/** Merge into WorkBuddyMCP core.mjs `actions` (optional integration). */
export const patchedActions = {
  update_member_basic: {
    label: '更新会员姓名电话（基本资料）',
    schema: {
      type: 'object',
      properties: {
        customerId: { type: 'string', pattern: '^[0-9]{1,20}$' },
        name: { type: 'string', maxLength: 80 },
        phone: { type: 'string', maxLength: 40 },
        remark: { type: 'string', maxLength: 255 },
      },
      required: ['customerId', 'name', 'phone'],
      additionalProperties: false,
    },
    method: 'PUT',
    route: (a) => `/api/customers/${a.customerId}`,
  },
  archive_member: {
    label: '停用会员（软删除，保留账务历史）',
    schema: {
      type: 'object',
      properties: {
        customerId: { type: 'string', pattern: '^[0-9]{1,20}$' },
      },
      required: ['customerId'],
      additionalProperties: false,
    },
    method: 'POST',
    route: (a) => `/api/customers/${a.customerId}/archive`,
  },
};
