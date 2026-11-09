    /**
     * Soft-archive (停用) a member. Ledger rows are retained.
     * Idempotent when already inactive. Does not permanently delete.
     */
    @PostMapping("/{id}/archive")
    public ApiResponse<?> archive(@PathVariable String id) {
        return ApiResponse.ok("会员已停用（软删除，账务历史保留）", barbershopService.archiveCustomer(id));
    }
