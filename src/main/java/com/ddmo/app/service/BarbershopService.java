package com.ddmo.app.service;

import com.ddmo.app.dto.ConsumeRequest;
import com.ddmo.app.dto.CustomerRequest;
import com.ddmo.app.dto.EmployeeRequest;
import com.ddmo.app.dto.RechargeRequest;
import com.ddmo.app.dto.ServiceTypeRequest;
import com.ddmo.app.model.AuditLog;
import com.ddmo.app.model.ConsumeRecord;
import com.ddmo.app.model.Customer;
import com.ddmo.app.model.Employee;
import com.ddmo.app.model.RechargeRecord;
import com.ddmo.app.model.ServiceType;
import com.ddmo.app.security.TenantContext;
import com.ddmo.app.util.SnowflakeIdGenerator;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

@Service
public class BarbershopService {

    private final JdbcTemplate jdbcTemplate;
    private final SnowflakeIdGenerator idGenerator;

    public BarbershopService(JdbcTemplate jdbcTemplate, SnowflakeIdGenerator idGenerator) {
        this.jdbcTemplate = jdbcTemplate;
        this.idGenerator = idGenerator;
    }

    public List<Customer> listCustomers(String keyword) {
        long tenantId = tenantId();
        String k = safeKeyword(keyword);
        return jdbcTemplate.query("""
                SELECT id, name, phone, verify_code, remark, status, created_at
                FROM t_customer
                WHERE tenant_id = ? AND (? = '' OR LOWER(name) LIKE LOWER(?) OR LOWER(phone) LIKE LOWER(?))
                ORDER BY created_at DESC
                """,
            (rs, i) -> new Customer(
                String.valueOf(rs.getLong("id")),
                rs.getString("name"),
                rs.getString("phone"),
                rs.getString("verify_code"),
                rs.getString("remark"),
                rs.getString("status"),
                rs.getTimestamp("created_at").toLocalDateTime()
            ),
            tenantId, k, "%" + k + "%", "%" + k + "%");
    }

    public Map<String, Object> listCustomersPaged(String keyword, int page, int size) {
        return paginate(listCustomers(keyword), page, size);
    }

    @Transactional
    public Customer createCustomer(CustomerRequest request) {
        long tenantId = tenantId();
        validateText(request.getName(), "会员姓名不能为空");
        validateText(request.getPhone(), "手机号不能为空");
        String phone = request.getPhone().trim();
        ensurePhoneUnique(tenantId, phone, null);
        String verifyCode = normalizeVerifyCode(request.getVerifyCode(), phone);

        long id = idGenerator.nextId();
        jdbcTemplate.update("""
                INSERT INTO t_customer(id, tenant_id, name, phone, verify_code, remark, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
            id, tenantId, request.getName().trim(), phone, verifyCode, defaultText(request.getRemark()));

        recordLog("CREATE_CUSTOMER", "customer", String.valueOf(id), "创建会员: " + request.getName().trim());

        BigDecimal init = request.getInitialRechargeAmount();
        if (init != null) {
            if (init.compareTo(BigDecimal.ZERO) < 0) {
                throw new IllegalArgumentException("初次充值金额不能小于0");
            }
            if (init.compareTo(BigDecimal.ZERO) > 0) {
                long rechargeId = idGenerator.nextId();
                jdbcTemplate.update("""
                        INSERT INTO t_recharge_record(id, tenant_id, customer_id, amount, remark, created_at)
                        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """,
                    rechargeId, tenantId, id, init, "初次充值");
                recordLog("CREATE_RECHARGE", "recharge", String.valueOf(rechargeId),
                    "会员 " + request.getName().trim() + " 初次充值 " + init);
            }
        }
        return getCustomerById(tenantId, String.valueOf(id));
    }

    @Transactional
    public Customer updateCustomer(String id, CustomerRequest request) {
        long tenantId = tenantId();
        Customer old = getCustomerById(tenantId, id);
        validateText(request.getName(), "会员姓名不能为空");
        validateText(request.getPhone(), "手机号不能为空");
        String phone = request.getPhone().trim();
        ensurePhoneUnique(tenantId, phone, id);
        String verifyCode = request.getVerifyCode() == null || request.getVerifyCode().isBlank()
            ? old.getVerifyCode()
            : normalizeVerifyCode(request.getVerifyCode(), phone);

        jdbcTemplate.update("""
                UPDATE t_customer
                SET name = ?, phone = ?, verify_code = ?, remark = ?, updated_at = CURRENT_TIMESTAMP
                WHERE tenant_id = ? AND id = ?
                """,
            request.getName().trim(), phone, verifyCode, defaultText(request.getRemark()), tenantId, parseId(id));
        recordLog("UPDATE_CUSTOMER", "customer", id, "更新会员: " + request.getName().trim());
        return getCustomerById(tenantId, id);
    }


    /**
     * One-way soft archive: active → inactive. History/recharge/consume rows stay.
     * Idempotent if already inactive. Permanent delete is not supported.
     * Existing product code does not refuse archive solely because balance &gt; 0;
     * balance is returned for human confirmation surfaces.
     */
    @Transactional
    public Map<String, Object> archiveCustomer(String id) {
        long tenantId = tenantId();
        Customer old = getCustomerById(tenantId, id);
        BigDecimal balance = getBalance(id);
        boolean already = !"active".equals(old.getStatus());
        if (!already) {
            jdbcTemplate.update(
                "UPDATE t_customer SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE tenant_id = ? AND id = ?",
                "inactive", tenantId, parseId(id));
            recordLog("DELETE_CUSTOMER", "customer", id, "停用会员: " + old.getName());
        }
        Customer now = getCustomerById(tenantId, id);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("customer", now);
        out.put("archived", true);
        out.put("idempotent", already);
        out.put("ledgerPreserved", true);
        out.put("balance", balance);
        out.put("permanentDelete", false);
        return out;
    }

    @Transactional
    public Customer toggleCustomerStatus(String id) {
        long tenantId = tenantId();
        Customer old = getCustomerById(tenantId, id);
        String next = "active".equals(old.getStatus()) ? "inactive" : "active";
        jdbcTemplate.update("UPDATE t_customer SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE tenant_id = ? AND id = ?",
            next, tenantId, parseId(id));
        recordLog("active".equals(next) ? "RESTORE_CUSTOMER" : "DELETE_CUSTOMER", "customer", id,
            ("active".equals(next) ? "恢复" : "停用") + "会员: " + old.getName());
        return getCustomerById(tenantId, id);
    }

    public List<Employee> listEmployees(String keyword) {
        long tenantId = tenantId();
        String k = safeKeyword(keyword);
        return jdbcTemplate.query("""
                SELECT id, name, status, created_at
                FROM t_employee
                WHERE tenant_id = ? AND (? = '' OR LOWER(name) LIKE LOWER(?))
                ORDER BY created_at DESC
                """,
            (rs, i) -> new Employee(
                String.valueOf(rs.getLong("id")),
                rs.getString("name"),
                rs.getString("status"),
                rs.getTimestamp("created_at").toLocalDateTime()
            ),
            tenantId, k, "%" + k + "%");
    }

    public Map<String, Object> listEmployeesPaged(String keyword, int page, int size) {
        return paginate(listEmployees(keyword), page, size);
    }

    @Transactional
    public Employee createEmployee(EmployeeRequest request) {
        long tenantId = tenantId();
        validateText(request.getName(), "员工姓名不能为空");
        long id = idGenerator.nextId();
        jdbcTemplate.update("""
                INSERT INTO t_employee(id, tenant_id, name, status, created_at, updated_at)
                VALUES (?, ?, ?, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, id, tenantId, request.getName().trim());
        recordLog("CREATE_EMPLOYEE", "employee", String.valueOf(id), "创建员工: " + request.getName().trim());
        return getEmployeeById(tenantId, String.valueOf(id));
    }

    @Transactional
    public Employee updateEmployee(String id, EmployeeRequest request) {
        long tenantId = tenantId();
        getEmployeeById(tenantId, id);
        validateText(request.getName(), "员工姓名不能为空");
        jdbcTemplate.update("UPDATE t_employee SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE tenant_id = ? AND id = ?",
            request.getName().trim(), tenantId, parseId(id));
        recordLog("UPDATE_EMPLOYEE", "employee", id, "更新员工: " + request.getName().trim());
        return getEmployeeById(tenantId, id);
    }

    @Transactional
    public Employee toggleEmployeeStatus(String id) {
        long tenantId = tenantId();
        Employee old = getEmployeeById(tenantId, id);
        String next = "active".equals(old.getStatus()) ? "inactive" : "active";
        jdbcTemplate.update("UPDATE t_employee SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE tenant_id = ? AND id = ?",
            next, tenantId, parseId(id));
        recordLog("active".equals(next) ? "RESTORE_EMPLOYEE" : "DISABLE_EMPLOYEE", "employee", id,
            ("active".equals(next) ? "恢复" : "停用") + "员工: " + old.getName());
        return getEmployeeById(tenantId, id);
    }

    public List<ServiceType> listServiceTypes() {
        long tenantId = tenantId();
        return jdbcTemplate.query("""
                SELECT id, name, price, status, created_at
                FROM t_service_type
                WHERE tenant_id = ?
                ORDER BY created_at DESC
                """,
            (rs, i) -> new ServiceType(
                String.valueOf(rs.getLong("id")),
                rs.getString("name"),
                rs.getBigDecimal("price"),
                rs.getString("status"),
                rs.getTimestamp("created_at").toLocalDateTime()
            ),
            tenantId
        );
    }

    @Transactional
    public ServiceType createServiceType(ServiceTypeRequest request) {
        long tenantId = tenantId();
        validateText(request.getName(), "服务名称不能为空");
        validateAmount(request.getPrice(), "价格必须大于等于0");
        long id = idGenerator.nextId();
        jdbcTemplate.update("""
                INSERT INTO t_service_type(id, tenant_id, name, price, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, id, tenantId, request.getName().trim(), request.getPrice());
        recordLog("CREATE_SERVICE", "service", String.valueOf(id), "新增服务: " + request.getName().trim());
        return getServiceById(tenantId, String.valueOf(id));
    }

    @Transactional
    public ServiceType updateServiceType(String id, ServiceTypeRequest request) {
        long tenantId = tenantId();
        getServiceById(tenantId, id);
        validateText(request.getName(), "服务名称不能为空");
        validateAmount(request.getPrice(), "价格必须大于等于0");
        jdbcTemplate.update("""
                UPDATE t_service_type SET name = ?, price = ?, updated_at = CURRENT_TIMESTAMP
                WHERE tenant_id = ? AND id = ?
                """, request.getName().trim(), request.getPrice(), tenantId, parseId(id));
        recordLog("UPDATE_SERVICE", "service", id, "更新服务: " + request.getName().trim());
        return getServiceById(tenantId, id);
    }

    @Transactional
    public ServiceType toggleServiceTypeStatus(String id) {
        long tenantId = tenantId();
        ServiceType old = getServiceById(tenantId, id);
        String next = "active".equals(old.getStatus()) ? "inactive" : "active";
        jdbcTemplate.update("UPDATE t_service_type SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE tenant_id = ? AND id = ?",
            next, tenantId, parseId(id));
        recordLog("active".equals(next) ? "RESTORE_SERVICE" : "DISABLE_SERVICE", "service", id,
            ("active".equals(next) ? "恢复" : "停用") + "服务: " + old.getName());
        return getServiceById(tenantId, id);
    }

    @Transactional
    public RechargeRecord createRecharge(RechargeRequest request) {
        long tenantId = tenantId();
        validateText(request.getCustomerId(), "会员不能为空");
        validateAmountPositive(request.getAmount(), "充值金额必须大于0");
        Customer customer = getCustomerById(tenantId, request.getCustomerId());
        ensureActive(customer.getStatus(), "会员已停用");
        long id = idGenerator.nextId();
        jdbcTemplate.update("""
                INSERT INTO t_recharge_record(id, tenant_id, customer_id, amount, remark, created_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, id, tenantId, parseId(request.getCustomerId()), request.getAmount(), defaultText(request.getRemark()));
        recordLog("CREATE_RECHARGE", "recharge", String.valueOf(id), "会员 " + customer.getName() + " 充值 " + request.getAmount());
        return getRechargeById(tenantId, String.valueOf(id));
    }

    @Transactional
    public ConsumeRecord createConsume(ConsumeRequest request) {
        long tenantId = tenantId();
        validateAmountPositive(request.getAmount(), "消费金额必须大于0");
        Customer customer = getCustomerById(tenantId, request.getCustomerId());
        Employee employee = getEmployeeById(tenantId, request.getEmployeeId());
        ServiceType serviceType = getServiceById(tenantId, request.getServiceTypeId());
        ensureActive(customer.getStatus(), "会员已停用");
        ensureActive(employee.getStatus(), "员工已停用");
        ensureActive(serviceType.getStatus(), "服务类型已停用");
        if (request.getVerifyCode() == null || request.getVerifyCode().isBlank()) {
            throw new IllegalArgumentException("请输入4位校验码");
        }
        if (!Objects.equals(customer.getVerifyCode(), request.getVerifyCode().trim())) {
            throw new IllegalArgumentException("校验码错误，无法消费");
        }
        if (getBalance(request.getCustomerId()).compareTo(request.getAmount()) < 0) {
            throw new IllegalArgumentException("余额不足，扣款失败");
        }

        long id = idGenerator.nextId();
        jdbcTemplate.update("""
                INSERT INTO t_consume_record(id, tenant_id, customer_id, employee_id, service_type_id, amount, remark, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
            id, tenantId, parseId(request.getCustomerId()), parseId(request.getEmployeeId()), parseId(request.getServiceTypeId()),
            request.getAmount(), defaultText(request.getRemark()));
        recordLog("CREATE_CONSUME", "consume", String.valueOf(id),
            "会员 " + customer.getName() + " 消费 " + request.getAmount() + "，员工 " + employee.getName());
        return getConsumeById(tenantId, String.valueOf(id));
    }

    public BigDecimal getBalance(String customerId) {
        long tenantId = tenantId();
        getCustomerById(tenantId, customerId);
        BigDecimal totalRecharge = jdbcTemplate.queryForObject(
            "SELECT COALESCE(SUM(amount),0) FROM t_recharge_record WHERE tenant_id = ? AND customer_id = ?",
            BigDecimal.class, tenantId, parseId(customerId));
        BigDecimal totalConsume = jdbcTemplate.queryForObject(
            "SELECT COALESCE(SUM(amount),0) FROM t_consume_record WHERE tenant_id = ? AND customer_id = ?",
            BigDecimal.class, tenantId, parseId(customerId));
        return totalRecharge.subtract(totalConsume);
    }

    public List<Map<String, Object>> listTransactionRows(String keyword) {
        long tenantId = tenantId();
        String k = safeKeyword(keyword);
        return jdbcTemplate.query("""
                SELECT x.id, x.type, x.customer_id, c.name AS customer_name, x.amount, x.detail, x.created_at
                FROM (
                    SELECT CAST(id AS TEXT) AS id, 'recharge' AS type, customer_id, amount, remark AS detail, created_at
                    FROM t_recharge_record WHERE tenant_id = ?
                    UNION ALL
                    SELECT CAST(cr.id AS TEXT) AS id, 'consume' AS type, cr.customer_id, cr.amount,
                           COALESCE(st.name,'未知服务') || '/' || COALESCE(e.name,'未知员工')
                               || CASE WHEN cr.remark = '' THEN '' ELSE '/' || cr.remark END AS detail,
                           cr.created_at
                    FROM t_consume_record cr
                    LEFT JOIN t_service_type st ON st.tenant_id = cr.tenant_id AND st.id = cr.service_type_id
                    LEFT JOIN t_employee e ON e.tenant_id = cr.tenant_id AND e.id = cr.employee_id
                    WHERE cr.tenant_id = ?
                ) x
                LEFT JOIN t_customer c ON c.tenant_id = ? AND c.id = x.customer_id
                WHERE (? = '' OR LOWER(c.name) LIKE LOWER(?) OR LOWER(x.detail) LIKE LOWER(?) OR LOWER(x.type) LIKE LOWER(?))
                ORDER BY x.created_at DESC
                """,
            (rs, i) -> {
                Map<String, Object> row = new HashMap<>();
                row.put("id", rs.getString("id"));
                row.put("type", rs.getString("type"));
                row.put("customerId", String.valueOf(rs.getLong("customer_id")));
                row.put("customerName", rs.getString("customer_name"));
                row.put("amount", rs.getBigDecimal("amount"));
                row.put("detail", rs.getString("detail"));
                row.put("createdAt", rs.getTimestamp("created_at").toLocalDateTime());
                return row;
            },
            tenantId, tenantId, tenantId, k, "%" + k + "%", "%" + k + "%", "%" + k + "%"
        );
    }

    public Map<String, Object> listTransactionRowsPaged(String keyword, int page, int size) {
        return paginate(listTransactionRows(keyword), page, size);
    }

    public List<AuditLog> listAuditLogs(String keyword) {
        long tenantId = tenantId();
        String k = safeKeyword(keyword);
        return jdbcTemplate.query("""
                SELECT id, action, entity_type, entity_id, detail, created_at
                FROM t_audit_log
                WHERE tenant_id = ? AND (? = '' OR LOWER(action) LIKE LOWER(?) OR LOWER(entity_type) LIKE LOWER(?) OR LOWER(detail) LIKE LOWER(?))
                ORDER BY created_at DESC
                """,
            (rs, i) -> new AuditLog(
                String.valueOf(rs.getLong("id")),
                rs.getString("action"),
                rs.getString("entity_type"),
                rs.getString("entity_id"),
                rs.getString("detail"),
                rs.getTimestamp("created_at").toLocalDateTime()
            ),
            tenantId, k, "%" + k + "%", "%" + k + "%", "%" + k + "%"
        );
    }

    public Map<String, Object> getDashboardSummary() {
        long tenantId = tenantId();
        BigDecimal totalRecharge = jdbcTemplate.queryForObject(
            "SELECT COALESCE(SUM(amount),0) FROM t_recharge_record WHERE tenant_id = ?", BigDecimal.class, tenantId);
        BigDecimal totalConsume = jdbcTemplate.queryForObject(
            "SELECT COALESCE(SUM(amount),0) FROM t_consume_record WHERE tenant_id = ?", BigDecimal.class, tenantId);

        Map<String, Object> map = new HashMap<>();
        map.put("activeCustomers", jdbcTemplate.queryForObject(
            "SELECT COUNT(1) FROM t_customer WHERE tenant_id = ? AND status = 'active'", Long.class, tenantId));
        map.put("totalCustomers", jdbcTemplate.queryForObject(
            "SELECT COUNT(1) FROM t_customer WHERE tenant_id = ?", Long.class, tenantId));
        map.put("activeEmployees", jdbcTemplate.queryForObject(
            "SELECT COUNT(1) FROM t_employee WHERE tenant_id = ? AND status = 'active'", Long.class, tenantId));
        map.put("totalBalance", totalRecharge.subtract(totalConsume));
        map.put("todayRecharge", jdbcTemplate.queryForObject(
            "SELECT COALESCE(SUM(amount),0) FROM t_recharge_record WHERE tenant_id = ? AND DATE(created_at) = DATE('now', 'localtime')",
            BigDecimal.class, tenantId));
        map.put("todayConsume", jdbcTemplate.queryForObject(
            "SELECT COALESCE(SUM(amount),0) FROM t_consume_record WHERE tenant_id = ? AND DATE(created_at) = DATE('now', 'localtime')",
            BigDecimal.class, tenantId));
        map.put("auditCount", jdbcTemplate.queryForObject(
            "SELECT COUNT(1) FROM t_audit_log WHERE tenant_id = ?", Long.class, tenantId));
        return map;
    }

    public Map<String, Object> getReportSummary(LocalDate start, LocalDate end) {
        long tenantId = tenantId();
        String fromDate = start.toString();
        String toDate = end.toString();
        Map<String, Object> map = new HashMap<>();
        map.put("total_recharge", jdbcTemplate.queryForObject(
            "SELECT COALESCE(SUM(amount),0) FROM t_recharge_record WHERE tenant_id = ? AND DATE(created_at) BETWEEN DATE(?) AND DATE(?)",
            BigDecimal.class, tenantId, fromDate, toDate));
        map.put("total_consume", jdbcTemplate.queryForObject(
            "SELECT COALESCE(SUM(amount),0) FROM t_consume_record WHERE tenant_id = ? AND DATE(created_at) BETWEEN DATE(?) AND DATE(?)",
            BigDecimal.class, tenantId, fromDate, toDate));
        map.put("total_customers", jdbcTemplate.queryForObject(
            "SELECT COUNT(1) FROM t_customer WHERE tenant_id = ?", Long.class, tenantId));
        map.put("new_customers", jdbcTemplate.queryForObject(
            "SELECT COUNT(1) FROM t_customer WHERE tenant_id = ? AND DATE(created_at) BETWEEN DATE(?) AND DATE(?)",
            Long.class, tenantId, fromDate, toDate));
        map.put("active_customers", jdbcTemplate.queryForObject(
            "SELECT COUNT(DISTINCT customer_id) FROM t_consume_record WHERE tenant_id = ? AND DATE(created_at) BETWEEN DATE(?) AND DATE(?)",
            Long.class, tenantId, fromDate, toDate));
        return map;
    }

    public List<Map<String, Object>> getEmployeePerformance(LocalDate start, LocalDate end) {
        long tenantId = tenantId();
        String fromDate = start.toString();
        String toDate = end.toString();
        List<Map<String, Object>> list = jdbcTemplate.query("""
                SELECT cr.employee_id, e.name AS employee_name, COUNT(1) AS total_count, COALESCE(SUM(cr.amount),0) AS total_amount
                FROM t_consume_record cr
                LEFT JOIN t_employee e ON e.tenant_id = cr.tenant_id AND e.id = cr.employee_id
                WHERE cr.tenant_id = ? AND DATE(cr.created_at) BETWEEN DATE(?) AND DATE(?)
                GROUP BY cr.employee_id, e.name
                ORDER BY total_amount DESC
                """,
            (rs, i) -> {
                Map<String, Object> row = new HashMap<>();
                int count = rs.getInt("total_count");
                BigDecimal totalAmount = rs.getBigDecimal("total_amount");
                row.put("employeeId", String.valueOf(rs.getLong("employee_id")));
                row.put("employeeName", rs.getString("employee_name"));
                row.put("total_count", count);
                row.put("total_amount", totalAmount);
                row.put("avg_amount", count == 0 ? BigDecimal.ZERO : totalAmount.divide(BigDecimal.valueOf(count), 2, RoundingMode.HALF_UP));
                return row;
            },
            tenantId, fromDate, toDate
        );
        return list;
    }

    public List<Map<String, Object>> getServiceBreakdown(LocalDate start, LocalDate end) {
        long tenantId = tenantId();
        String fromDate = start.toString();
        String toDate = end.toString();
        return jdbcTemplate.query("""
                SELECT cr.service_type_id, st.name AS service_name, COUNT(1) AS total_count, COALESCE(SUM(cr.amount),0) AS total_amount
                FROM t_consume_record cr
                LEFT JOIN t_service_type st ON st.tenant_id = cr.tenant_id AND st.id = cr.service_type_id
                WHERE cr.tenant_id = ? AND DATE(cr.created_at) BETWEEN DATE(?) AND DATE(?)
                GROUP BY cr.service_type_id, st.name
                ORDER BY total_amount DESC
                """,
            (rs, i) -> {
                Map<String, Object> row = new HashMap<>();
                row.put("serviceTypeId", String.valueOf(rs.getLong("service_type_id")));
                row.put("serviceName", rs.getString("service_name"));
                row.put("total_count", rs.getInt("total_count"));
                row.put("total_amount", rs.getBigDecimal("total_amount"));
                return row;
            },
            tenantId, fromDate, toDate
        );
    }

    private Customer getCustomerById(long tenantId, String id) {
        List<Customer> list = jdbcTemplate.query("""
                SELECT id, name, phone, verify_code, remark, status, created_at
                FROM t_customer WHERE tenant_id = ? AND id = ?
                """,
            (rs, i) -> new Customer(
                String.valueOf(rs.getLong("id")),
                rs.getString("name"),
                rs.getString("phone"),
                rs.getString("verify_code"),
                rs.getString("remark"),
                rs.getString("status"),
                rs.getTimestamp("created_at").toLocalDateTime()
            ),
            tenantId, parseId(id));
        if (list.isEmpty()) throw new IllegalArgumentException("会员不存在");
        return list.get(0);
    }

    private Employee getEmployeeById(long tenantId, String id) {
        List<Employee> list = jdbcTemplate.query("""
                SELECT id, name, status, created_at
                FROM t_employee WHERE tenant_id = ? AND id = ?
                """,
            (rs, i) -> new Employee(
                String.valueOf(rs.getLong("id")),
                rs.getString("name"),
                rs.getString("status"),
                rs.getTimestamp("created_at").toLocalDateTime()
            ),
            tenantId, parseId(id));
        if (list.isEmpty()) throw new IllegalArgumentException("员工不存在");
        return list.get(0);
    }

    private ServiceType getServiceById(long tenantId, String id) {
        List<ServiceType> list = jdbcTemplate.query("""
                SELECT id, name, price, status, created_at
                FROM t_service_type WHERE tenant_id = ? AND id = ?
                """,
            (rs, i) -> new ServiceType(
                String.valueOf(rs.getLong("id")),
                rs.getString("name"),
                rs.getBigDecimal("price"),
                rs.getString("status"),
                rs.getTimestamp("created_at").toLocalDateTime()
            ),
            tenantId, parseId(id));
        if (list.isEmpty()) throw new IllegalArgumentException("服务类型不存在");
        return list.get(0);
    }

    private RechargeRecord getRechargeById(long tenantId, String id) {
        List<RechargeRecord> list = jdbcTemplate.query("""
                SELECT id, customer_id, amount, remark, created_at
                FROM t_recharge_record WHERE tenant_id = ? AND id = ?
                """,
            (rs, i) -> new RechargeRecord(
                String.valueOf(rs.getLong("id")),
                String.valueOf(rs.getLong("customer_id")),
                rs.getBigDecimal("amount"),
                rs.getString("remark"),
                rs.getTimestamp("created_at").toLocalDateTime()
            ),
            tenantId, parseId(id));
        if (list.isEmpty()) throw new IllegalArgumentException("充值记录不存在");
        return list.get(0);
    }

    private ConsumeRecord getConsumeById(long tenantId, String id) {
        List<ConsumeRecord> list = jdbcTemplate.query("""
                SELECT id, customer_id, employee_id, service_type_id, amount, remark, created_at
                FROM t_consume_record WHERE tenant_id = ? AND id = ?
                """,
            (rs, i) -> new ConsumeRecord(
                String.valueOf(rs.getLong("id")),
                String.valueOf(rs.getLong("customer_id")),
                String.valueOf(rs.getLong("employee_id")),
                String.valueOf(rs.getLong("service_type_id")),
                rs.getBigDecimal("amount"),
                rs.getString("remark"),
                rs.getTimestamp("created_at").toLocalDateTime()
            ),
            tenantId, parseId(id));
        if (list.isEmpty()) throw new IllegalArgumentException("消费记录不存在");
        return list.get(0);
    }

    private void ensurePhoneUnique(long tenantId, String phone, String currentId) {
        String sql = currentId == null
            ? "SELECT COUNT(1) FROM t_customer WHERE tenant_id = ? AND phone = ?"
            : "SELECT COUNT(1) FROM t_customer WHERE tenant_id = ? AND phone = ? AND id <> ?";
        Long count = currentId == null
            ? jdbcTemplate.queryForObject(sql, Long.class, tenantId, phone)
            : jdbcTemplate.queryForObject(sql, Long.class, tenantId, phone, parseId(currentId));
        if (count != null && count > 0) {
            throw new IllegalArgumentException("手机号必须唯一");
        }
    }

    private void recordLog(String action, String entityType, String entityId, String detail) {
        long id = idGenerator.nextId();
        jdbcTemplate.update("""
                INSERT INTO t_audit_log(id, tenant_id, action, entity_type, entity_id, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
            id, tenantId(), toZhAction(action), toZhEntityType(entityType), entityId, detail);
    }

    private String toZhAction(String action) {
        if (action == null) return "未知操作";
        return switch (action) {
            case "CREATE_CUSTOMER" -> "创建会员";
            case "UPDATE_CUSTOMER" -> "更新会员";
            case "DELETE_CUSTOMER" -> "停用会员";
            case "RESTORE_CUSTOMER" -> "恢复会员";
            case "CREATE_EMPLOYEE" -> "创建员工";
            case "UPDATE_EMPLOYEE" -> "更新员工";
            case "DISABLE_EMPLOYEE" -> "停用员工";
            case "RESTORE_EMPLOYEE" -> "恢复员工";
            case "CREATE_SERVICE" -> "创建服务";
            case "UPDATE_SERVICE" -> "更新服务";
            case "DISABLE_SERVICE" -> "停用服务";
            case "RESTORE_SERVICE" -> "恢复服务";
            case "CREATE_RECHARGE" -> "创建充值";
            case "CREATE_CONSUME" -> "创建消费";
            case "INIT" -> "系统初始化";
            default -> action;
        };
    }

    private String toZhEntityType(String entityType) {
        if (entityType == null) return "未知实体";
        return switch (entityType) {
            case "customer" -> "会员";
            case "employee" -> "员工";
            case "service" -> "服务类型";
            case "recharge" -> "充值记录";
            case "consume" -> "消费记录";
            case "system" -> "系统";
            default -> entityType;
        };
    }

    private Map<String, Object> paginate(List<?> all, int page, int size) {
        int safeSize = size <= 0 ? 10 : Math.min(size, 100);
        int safePage = Math.max(page, 1);
        int total = all.size();
        int totalPages = total == 0 ? 1 : (int) Math.ceil(total / (double) safeSize);
        if (safePage > totalPages) safePage = totalPages;
        int from = (safePage - 1) * safeSize;
        int to = Math.min(from + safeSize, total);
        List<?> items = from >= to ? List.of() : all.subList(from, to);
        Map<String, Object> data = new HashMap<>();
        data.put("items", items);
        data.put("page", safePage);
        data.put("size", safeSize);
        data.put("total", total);
        data.put("totalPages", totalPages);
        return data;
    }

    private long tenantId() {
        return TenantContext.getTenantId();
    }

    private long parseId(String id) {
        try {
            return Long.parseLong(id);
        } catch (Exception e) {
            throw new IllegalArgumentException("ID非法: " + id);
        }
    }

    private String defaultText(String text) {
        return text == null ? "" : text.trim();
    }

    private String safeKeyword(String keyword) {
        return keyword == null ? "" : keyword.trim();
    }

    private void validateText(String value, String message) {
        if (value == null || value.trim().isEmpty()) throw new IllegalArgumentException(message);
    }

    private void validateAmount(BigDecimal value, String message) {
        if (value == null || value.compareTo(BigDecimal.ZERO) < 0) throw new IllegalArgumentException(message);
    }

    private void validateAmountPositive(BigDecimal value, String message) {
        if (value == null || value.compareTo(BigDecimal.ZERO) <= 0) throw new IllegalArgumentException(message);
    }

    private void ensureActive(String status, String message) {
        if (!"active".equals(status)) throw new IllegalArgumentException(message);
    }

    private String normalizeVerifyCode(String verifyCode, String phone) {
        String v = (verifyCode == null || verifyCode.isBlank()) ? last4(phone) : verifyCode.trim();
        if (!v.matches("\\d{4}")) throw new IllegalArgumentException("校验码必须是4位数字");
        return v;
    }

    private String last4(String phone) {
        String p = phone == null ? "" : phone.trim();
        if (p.length() < 4) throw new IllegalArgumentException("手机号格式错误");
        return p.substring(p.length() - 4);
    }
}
