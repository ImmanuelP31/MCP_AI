from mcp_ops_auth.rbac import Permission, Role, has_permission


def test_viewer_has_read_permissions_only() -> None:
    assert has_permission(Role.VIEWER, Permission.DEVICES_READ)
    assert has_permission(Role.VIEWER, Permission.KNOWLEDGE_READ)
    assert not has_permission(Role.VIEWER, Permission.DEVICES_OPERATE)


def test_operator_can_operate_devices() -> None:
    assert has_permission(Role.OPERATOR, Permission.DEVICES_OPERATE)


def test_admin_has_all_permissions() -> None:
    for permission in Permission:
        assert has_permission(Role.ADMIN, permission)
