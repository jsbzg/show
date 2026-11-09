package com.ddmo.app.controller;

import com.ddmo.app.dto.ApiResponse;
import com.ddmo.app.dto.CustomerRequest;
import com.ddmo.app.model.Customer;
import com.ddmo.app.service.BarbershopService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final BarbershopService barbershopService;

    public CustomerController(BarbershopService barbershopService) {
        this.barbershopService = barbershopService;
    }

    @GetMapping
    public ApiResponse<?> list(
        @RequestParam(required = false) String keyword,
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(defaultValue = "10") int size
    ) {
        return ApiResponse.ok(barbershopService.listCustomersPaged(keyword, page, size));
    }

    @PostMapping
    public ApiResponse<Customer> create(@RequestBody CustomerRequest request) {
        return ApiResponse.ok("创建成功", barbershopService.createCustomer(request));
    }

    @PutMapping("/{id}")
    public ApiResponse<Customer> update(@PathVariable String id, @RequestBody CustomerRequest request) {
        return ApiResponse.ok("更新成功", barbershopService.updateCustomer(id, request));
    }

    @PatchMapping("/{id}/toggle-status")
    public ApiResponse<Customer> toggleStatus(@PathVariable String id) {
        return ApiResponse.ok("状态已更新", barbershopService.toggleCustomerStatus(id));
    }

    /**
     * Soft-archive (停用) a member. Ledger rows are retained.
     * Idempotent when already inactive. Does not permanently delete.
     */
    @PostMapping("/{id}/archive")
    public ApiResponse<?> archive(@PathVariable String id) {
        return ApiResponse.ok("会员已停用（软删除，账务历史保留）", barbershopService.archiveCustomer(id));
    }
}

