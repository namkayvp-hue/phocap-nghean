from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
VERSION = "MENU-SO-XUONG-V1.3-DAY-DU-CHUC-NANG"
PARTIAL_REL = Path("app/templates/partials/dropdown_menu_v1.html")
MAIN_REL = Path("app/main.py")
DB_REL = Path("data/phocap.db")
INCLUDE_MARKER = '{% include "partials/dropdown_menu_v1.html" %}'

EXCLUDED_TEMPLATES = {
    "auth/login.html",
    "surveys/field_print.html",
}

MENU_TEMPLATE = '{# ============================================================\n   MENU SỔ XUỐNG V1.3 - ĐẦY ĐỦ CHỨC NĂNG\n   Mục tiêu:\n   - Thanh menu dùng chung cho mọi giao diện con sau đăng nhập.\n   - Menu cấp 1 xổ xuống; nhóm nghiệp vụ bên trong tiếp tục xổ ngang.\n   - Chỉ điều hướng giao diện.\n   - Không thay đổi route, dữ liệu hoặc nghiệp vụ.\n   - Giữ nguyên các liên kết/route đã có trong Menu V1.\n   ============================================================ #}\n<style id="pc-menu-v13-inline-style">\n.pc-global-nav,\n.pc-global-nav * {\n    box-sizing: border-box;\n}\n\n.pc-global-nav {\n    position: sticky;\n    top: 0;\n    z-index: 5000;\n    width: 100%;\n    font-family: Arial, Helvetica, sans-serif;\n    color: #ffffff;\n    background: #ffffff;\n    box-shadow: 0 3px 12px rgba(18, 52, 86, 0.18);\n}\n\n.pc-global-nav__top {\n    min-height: 56px;\n    padding: 7px max(18px, calc((100% - 1280px) / 2));\n    display: flex;\n    align-items: center;\n    justify-content: space-between;\n    gap: 18px;\n    background: linear-gradient(90deg, #0d47a1 0%, #1565c0 58%, #1976d2 100%);\n}\n\n.pc-global-nav__brand {\n    min-width: 0;\n    display: inline-flex;\n    align-items: center;\n    gap: 10px;\n    color: #ffffff !important;\n    text-decoration: none !important;\n}\n\n.pc-global-nav__brand-mark {\n    width: 36px;\n    height: 36px;\n    flex: 0 0 36px;\n    display: inline-flex;\n    align-items: center;\n    justify-content: center;\n    border-radius: 8px;\n    background: #ffffff;\n    color: #0d47a1;\n    font-size: 14px;\n    font-weight: 800;\n}\n\n.pc-global-nav__brand-text {\n    min-width: 0;\n    display: flex;\n    flex-direction: column;\n    line-height: 1.15;\n}\n\n.pc-global-nav__brand-text strong {\n    color: #ffffff;\n    font-size: 14px;\n    letter-spacing: .25px;\n    white-space: nowrap;\n}\n\n.pc-global-nav__brand-text small {\n    margin-top: 3px;\n    color: rgba(255,255,255,.9);\n    font-size: 11px;\n}\n\n.pc-global-nav__account {\n    display: grid;\n    grid-template-columns: minmax(0, auto) auto;\n    grid-template-areas: "name logout" "unit logout";\n    align-items: center;\n    column-gap: 12px;\n    text-align: right;\n}\n\n.pc-global-nav__account-name {\n    grid-area: name;\n    color: #ffffff;\n    font-size: 14px;\n    font-weight: 700;\n}\n\n.pc-global-nav__account-unit {\n    grid-area: unit;\n    max-width: 460px;\n    overflow: hidden;\n    text-overflow: ellipsis;\n    white-space: nowrap;\n    color: rgba(255,255,255,.9);\n    font-size: 11px;\n}\n\n.pc-global-nav__logout-form {\n    grid-area: logout;\n    margin: 0 !important;\n}\n\n.pc-global-nav__logout {\n    min-height: 34px;\n    padding: 7px 12px;\n    border: 1px solid rgba(255,255,255,.62);\n    border-radius: 7px;\n    background: rgba(255,255,255,.12);\n    color: #ffffff;\n    font: inherit;\n    font-size: 12px;\n    font-weight: 700;\n    cursor: pointer;\n}\n\n.pc-global-nav__logout:hover,\n.pc-global-nav__logout:focus-visible {\n    background: #ffffff;\n    color: #0d47a1;\n    outline: none;\n}\n\n.pc-global-nav__bar {\n    min-height: 43px;\n    padding: 0 max(18px, calc((100% - 1280px) / 2));\n    display: flex;\n    align-items: stretch;\n    gap: 0;\n    background: #ffffff;\n    border-bottom: 1px solid #d8e1eb;\n    color: #25364a;\n    overflow: visible;\n}\n\n.pc-global-nav__home,\n.pc-menu-trigger {\n    min-height: 43px;\n    margin: 0;\n    padding: 0 15px;\n    display: inline-flex;\n    align-items: center;\n    justify-content: center;\n    gap: 6px;\n    border: 0;\n    border-right: 1px solid #e5ebf1;\n    border-radius: 0;\n    background: transparent;\n    color: #25364a !important;\n    font: inherit;\n    font-size: 14px;\n    font-weight: 600;\n    line-height: 1.2;\n    text-decoration: none !important;\n    white-space: nowrap;\n    cursor: pointer;\n    box-shadow: none;\n}\n\n.pc-global-nav__home:hover,\n.pc-global-nav__home:focus-visible,\n.pc-menu-trigger:hover,\n.pc-menu-trigger:focus-visible,\n.pc-menu-group.is-open > .pc-menu-trigger,\n.pc-menu-group.is-active > .pc-menu-trigger,\n.pc-global-nav__home.is-active {\n    background: #eaf3ff;\n    color: #0d5fb8 !important;\n    outline: none;\n}\n\n.pc-menu-group {\n    position: relative;\n    display: flex;\n    align-items: stretch;\n}\n\n.pc-menu-caret {\n    font-size: 11px;\n    transition: transform .16s ease;\n}\n\n.pc-menu-group.is-open > .pc-menu-trigger .pc-menu-caret {\n    transform: rotate(180deg);\n}\n\n.pc-dropdown {\n    position: absolute;\n    top: 100%;\n    left: 0;\n    z-index: 5100;\n    width: max-content;\n    min-width: 300px;\n    max-width: min(430px, calc(100vw - 28px));\n    padding: 6px 0;\n    display: none;\n    background: #ffffff;\n    border: 1px solid #d9e2ec;\n    border-radius: 0 0 8px 8px;\n    box-shadow: 0 12px 28px rgba(30,53,79,.18);\n}\n\n.pc-menu-group.is-open > .pc-dropdown,\n.pc-menu-group:focus-within > .pc-dropdown {\n    display: block;\n}\n\n.pc-dropdown--right {\n    left: auto;\n    right: 0;\n}\n\n.pc-dropdown > a,\n.pc-submenu-trigger,\n.pc-submenu-panel > a {\n    width: 100%;\n    min-height: 39px;\n    margin: 0;\n    padding: 9px 14px;\n    display: flex;\n    align-items: center;\n    gap: 10px;\n    border: 0;\n    border-radius: 0;\n    background: #ffffff;\n    color: #26384d !important;\n    font: inherit;\n    font-size: 13px;\n    font-weight: 500;\n    line-height: 1.35;\n    text-align: left;\n    text-decoration: none !important;\n    white-space: normal;\n    cursor: pointer;\n}\n\n.pc-dropdown > a:hover,\n.pc-dropdown > a:focus-visible,\n.pc-submenu-trigger:hover,\n.pc-submenu-trigger:focus-visible,\n.pc-submenu.is-open > .pc-submenu-trigger,\n.pc-submenu:focus-within > .pc-submenu-trigger,\n.pc-submenu-panel > a:hover,\n.pc-submenu-panel > a:focus-visible {\n    background: #eaf3ff;\n    color: #0d5fb8 !important;\n    outline: none;\n}\n\n.pc-submenu {\n    position: relative;\n}\n\n.pc-submenu-trigger {\n    justify-content: space-between;\n    font-weight: 600;\n}\n\n.pc-submenu-trigger__text {\n    min-width: 0;\n    display: inline-flex;\n    align-items: center;\n    gap: 8px;\n}\n\n.pc-submenu-arrow {\n    flex: 0 0 auto;\n    color: #708196;\n    font-size: 12px;\n    line-height: 1;\n}\n\n.pc-submenu-panel {\n    position: absolute;\n    top: -7px;\n    left: calc(100% - 2px);\n    z-index: 5200;\n    width: max-content;\n    min-width: 315px;\n    max-width: min(430px, calc(100vw - 28px));\n    padding: 6px 0;\n    display: none;\n    background: #ffffff;\n    border: 1px solid #d9e2ec;\n    border-radius: 7px;\n    box-shadow: 0 12px 28px rgba(30,53,79,.18);\n}\n\n.pc-submenu.is-open > .pc-submenu-panel,\n.pc-submenu:focus-within > .pc-submenu-panel {\n    display: block;\n}\n\n.pc-submenu.opens-left > .pc-submenu-panel,\n.pc-dropdown--right .pc-submenu > .pc-submenu-panel {\n    right: calc(100% - 2px);\n    left: auto;\n}\n\n.pc-dropdown__section-title {\n    padding: 7px 14px 6px;\n    color: #8190a1;\n    font-size: 11px;\n    font-weight: 800;\n    letter-spacing: .45px;\n    text-transform: uppercase;\n}\n\n.pc-dropdown__divider {\n    height: 1px;\n    margin: 5px 10px;\n    background: #e8edf3;\n}\n\n.pc-dropdown__note {\n    margin: 5px 10px;\n    padding: 9px 10px;\n    display: block;\n    border-radius: 6px;\n    background: #f5f8fb;\n    color: #617286;\n    font-size: 12px;\n    line-height: 1.45;\n}\n\n.pc-submenu-panel .pc-dropdown__note {\n    margin: 5px 10px;\n}\n\n@media (hover: hover) and (pointer: fine) {\n    .pc-submenu:hover > .pc-submenu-panel {\n        display: block;\n    }\n\n    .pc-submenu:hover > .pc-submenu-trigger {\n        background: #eaf3ff;\n        color: #0d5fb8 !important;\n    }\n}\n\n@media (max-width: 1100px) {\n    .pc-global-nav__account-unit {\n        max-width: 260px;\n    }\n\n    .pc-global-nav__bar {\n        padding-inline: 8px;\n    }\n\n    .pc-global-nav__home,\n    .pc-menu-trigger {\n        padding-inline: 11px;\n    }\n}\n\n@media (max-width: 760px) {\n    .pc-global-nav {\n        position: relative;\n    }\n\n    .pc-global-nav__top {\n        flex-direction: column;\n        align-items: stretch;\n        gap: 8px;\n    }\n\n    .pc-global-nav__brand-text strong {\n        white-space: normal;\n    }\n\n    .pc-global-nav__account {\n        grid-template-columns: 1fr auto;\n        text-align: left;\n    }\n\n    .pc-global-nav__account-unit {\n        max-width: 100%;\n    }\n\n    .pc-global-nav__bar {\n        flex-wrap: wrap;\n        overflow: visible;\n        padding: 4px 8px;\n    }\n\n    .pc-global-nav__home,\n    .pc-menu-trigger {\n        min-height: 40px;\n        border-right: 0;\n        border-radius: 6px;\n    }\n\n    .pc-dropdown,\n    .pc-dropdown--right {\n        position: fixed;\n        top: 105px;\n        right: 10px;\n        left: 10px;\n        width: auto;\n        max-width: none;\n        max-height: calc(100vh - 120px);\n        overflow-y: auto;\n        border-radius: 8px;\n    }\n\n    .pc-submenu-panel,\n    .pc-submenu.opens-left > .pc-submenu-panel,\n    .pc-dropdown--right .pc-submenu > .pc-submenu-panel {\n        position: static;\n        width: auto;\n        min-width: 0;\n        max-width: none;\n        margin: 0 8px 6px 18px;\n        padding: 3px 0;\n        border: 0;\n        border-left: 3px solid #d6e7fb;\n        border-radius: 0;\n        box-shadow: none;\n    }\n\n    .pc-submenu-panel > a {\n        min-height: 36px;\n        padding-left: 13px;\n        font-size: 12.5px;\n    }\n\n    .pc-submenu-arrow {\n        transform: rotate(90deg);\n    }\n}\n\n\n/* V1.3: bỏ các ô chọn/truy cập nhanh đã được chuyển lên menu.\n   Chỉ ẩn phần điều hướng trùng lặp; không ẩn biểu mẫu, bảng dữ liệu hay thẻ thống kê. */\n.roles,\n.survey-menu-grid,\n.quick-access-grid,\n.catalog {\n    display: none !important;\n}\n\n.pc-batch-link-needs-selection::after {\n    content: " · chọn đợt";\n    margin-left: auto;\n    color: #8a96a4;\n    font-size: 11px;\n    font-weight: 600;\n}\n\n@media print {\n    .pc-global-nav {\n        display: none !important;\n    }\n}\n</style>\n\n{% set menu_user = nguoi_dung if nguoi_dung is defined and nguoi_dung else (request.scope.get(\'auth_user\') if request is defined else none) %}\n{% if menu_user %}\n    {% set menu_role = (menu_user.role_code or \'\')|upper %}\n    {% set menu_path = request.url.path if request is defined else \'/\' %}\n\n    <nav class="pc-global-nav" aria-label="Điều hướng chính">\n        <div class="pc-global-nav__top">\n            <a class="pc-global-nav__brand" href="/" title="Về trang chủ">\n                <span class="pc-global-nav__brand-mark">PC</span>\n                <span class="pc-global-nav__brand-text">\n                    <strong>PHỔ CẬP GIÁO DỤC MẦM NON</strong>\n                    <small>Hệ thống quản lý dữ liệu</small>\n                </span>\n            </a>\n\n            <div class="pc-global-nav__account">\n                <span class="pc-global-nav__account-name">{{ menu_user.full_name }}</span>\n                <span class="pc-global-nav__account-unit">{{ menu_user.role_name }} · {{ menu_user.unit_name }}</span>\n                <form method="post" action="/dang-xuat" class="pc-global-nav__logout-form">\n                    <button type="submit" class="pc-global-nav__logout">Đăng xuất</button>\n                </form>\n            </div>\n        </div>\n\n        <div class="pc-global-nav__bar" data-pc-dropdown-menu-v13>\n            <a class="pc-global-nav__home {% if menu_path == \'/\' %}is-active{% endif %}" href="/">\n                Trang chủ\n            </a>\n\n            {% if menu_role in [\'ADMIN\', \'SO\'] %}\n                <div class="pc-menu-group {% if menu_path.startswith(\'/tai-khoan\') or menu_path.startswith(\'/xa\') or menu_path.startswith(\'/truong\') %}is-active{% endif %}">\n                    <button type="button" class="pc-menu-trigger" aria-expanded="false">\n                        1. Danh mục <span class="pc-menu-caret">▾</span>\n                    </button>\n                    <div class="pc-dropdown" role="menu">\n                        <div class="pc-submenu">\n                            <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                                <span class="pc-submenu-trigger__text">1.1. Quản lý tài khoản</span>\n                                <span class="pc-submenu-arrow">▶</span>\n                            </button>\n                            <div class="pc-submenu-panel" role="menu">\n                                <a href="/tai-khoan?muc=phong_ban" role="menuitem">1.1.1. Tài khoản Phòng ban</a>\n                                <a href="/tai-khoan?muc=xa" role="menuitem">1.1.2. Tài khoản Xã/phường</a>\n                                <a href="/tai-khoan?muc=truong" role="menuitem">1.1.3. Tài khoản Trường mầm non</a>\n                                <a href="/tai-khoan?muc=tra_cuu" role="menuitem">1.1.4. Tra cứu toàn hệ thống</a>\n                                <a href="/tai-khoan/cap-dong-loat/xem-truoc" role="menuitem">1.1.5. Cấp tài khoản đồng loạt</a>\n                                <a href="/tai-khoan/xuat-don-vi-chua-cap-excel" role="menuitem">1.1.6. Xuất đơn vị chưa cấp Excel</a>\n                            </div>\n                        </div>\n\n                        <div class="pc-submenu">\n                            <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                                <span class="pc-submenu-trigger__text">1.2. Đơn vị hành chính</span>\n                                <span class="pc-submenu-arrow">▶</span>\n                            </button>\n                            <div class="pc-submenu-panel" role="menu">\n                                <a href="/xa" role="menuitem">1.2.1. Danh mục Xã/phường</a>\n                                <a href="/truong" role="menuitem">1.2.2. Danh mục Trường</a>\n                            </div>\n                        </div>\n                    </div>\n                </div>\n            {% elif menu_role == \'XA\' %}\n                <div class="pc-menu-group {% if menu_path.startswith(\'/truong\') %}is-active{% endif %}">\n                    <button type="button" class="pc-menu-trigger" aria-expanded="false">\n                        1. Danh mục <span class="pc-menu-caret">▾</span>\n                    </button>\n                    <div class="pc-dropdown" role="menu">\n                        <div class="pc-submenu">\n                            <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                                <span class="pc-submenu-trigger__text">1.1. Đơn vị thuộc xã/phường</span>\n                                <span class="pc-submenu-arrow">▶</span>\n                            </button>\n                            <div class="pc-submenu-panel" role="menu">\n                                <a href="/truong" role="menuitem">1.1.1. Danh sách trường thuộc xã/phường</a>\n                            </div>\n                        </div>\n                    </div>\n                </div>\n            {% elif menu_role == \'TRUONG\' %}\n                <div class="pc-menu-group {% if menu_path.startswith(\'/tai-khoan\') %}is-active{% endif %}">\n                    <button type="button" class="pc-menu-trigger" aria-expanded="false">\n                        1. Danh mục <span class="pc-menu-caret">▾</span>\n                    </button>\n                    <div class="pc-dropdown" role="menu">\n                        <div class="pc-submenu">\n                            <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                                <span class="pc-submenu-trigger__text">1.1. Tài khoản giáo viên</span>\n                                <span class="pc-submenu-arrow">▶</span>\n                            </button>\n                            <div class="pc-submenu-panel" role="menu">\n                                <a href="/tai-khoan" role="menuitem">1.1.1. Quản lý tài khoản giáo viên</a>\n                            </div>\n                        </div>\n                    </div>\n                </div>\n            {% endif %}\n\n            <div class="pc-menu-group {% if menu_path.startswith(\'/dieu-tra\') %}is-active{% endif %}">\n                <button type="button" class="pc-menu-trigger" aria-expanded="false">\n                    2. Điều tra hộ dân <span class="pc-menu-caret">▾</span>\n                </button>\n                <div class="pc-dropdown" role="menu">\n                    <div class="pc-submenu">\n                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                            <span class="pc-submenu-trigger__text">2.1. Đợt điều tra</span>\n                            <span class="pc-submenu-arrow">▶</span>\n                        </button>\n                        <div class="pc-submenu-panel" role="menu">\n                            <a href="/dieu-tra" role="menuitem">2.1.1. Danh sách đợt điều tra</a>\n                            {% if menu_role in [\'ADMIN\', \'SO\'] %}\n                                <a href="/dieu-tra/khoi-tao-nam-hoc-toan-tinh" role="menuitem">2.1.2. Khởi tạo năm học toàn tỉnh</a>\n                                <a href="/dieu-tra/dieu-hanh-trien-khai" role="menuitem">2.1.3. Điều hành triển khai toàn tỉnh</a>\n                            {% endif %}\n                            {% if menu_role in [\'ADMIN\', \'SO\', \'PHONG_BAN\', \'XA\'] %}\n                                <a href="/dieu-tra/du-lieu-lich-su" role="menuitem">2.1.4. Trung tâm dữ liệu lịch sử</a>\n                                <a href="/dieu-tra/trung-tam-phieu" role="menuitem">2.1.5. Trung tâm phiếu điều tra</a>\n                            {% endif %}\n                        </div>\n                    </div>\n\n                    <div class="pc-submenu">\n                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                            <span class="pc-submenu-trigger__text">2.2. Hộ dân và phân công</span>\n                            <span class="pc-submenu-arrow">▶</span>\n                        </button>\n                        <div class="pc-submenu-panel" role="menu">\n                            <a href="/dieu-tra" data-batch-template="/dieu-tra/{batch_id}/ho-dan" role="menuitem">2.2.1. Danh sách hộ dân</a>\n                            <a href="/dieu-tra" data-batch-template="/dieu-tra/{batch_id}/phieu-in-thuc-dia" role="menuitem">2.2.2. In phiếu điều tra</a>\n                            <a href="/dieu-tra" data-batch-template="/dieu-tra/{batch_id}/ho-dan/xuat-excel" role="menuitem">2.2.3. Xuất Excel điều tra</a>\n                            <a href="/dieu-tra" data-batch-template="/dieu-tra/{batch_id}/ho-dan/nhap-excel" role="menuitem">2.2.4. Nhập Excel cập nhật hộ dân</a>\n\n                            {% if menu_role in [\'ADMIN\', \'SO\', \'XA\'] %}\n                                <a href="/dieu-tra" data-batch-template="/dieu-tra/{batch_id}/phan-cong-truong" role="menuitem">2.2.5. Phân công trường</a>\n                                <a href="/dieu-tra" data-batch-template="/dieu-tra/{batch_id}/giao-phieu-truong" role="menuitem">2.2.6. Giao phiếu cho trường</a>\n                            {% endif %}\n\n                            {% if menu_role in [\'ADMIN\', \'SO\', \'XA\', \'TRUONG\'] %}\n                                <a href="/dieu-tra" data-batch-template="/dieu-tra/{batch_id}/phan-cong-hang-loat" role="menuitem">2.2.7. Phân công hàng loạt</a>\n                            {% endif %}\n\n                            {% if menu_role == \'TRUONG\' %}\n                                <a href="/dieu-tra" data-batch-template="/dieu-tra/{batch_id}/giao-phieu-giao-vien" role="menuitem">2.2.8. Giao phiếu cho giáo viên</a>\n                            {% endif %}\n                        </div>\n                    </div>\n\n                    <div class="pc-submenu">\n                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                            <span class="pc-submenu-trigger__text">2.3. Kiểm tra, tiến độ và chốt</span>\n                            <span class="pc-submenu-arrow">▶</span>\n                        </button>\n                        <div class="pc-submenu-panel" role="menu">\n                            <a href="/dieu-tra" data-batch-template="/dieu-tra/{batch_id}/kiem-tra-du-lieu" role="menuitem">2.3.1. Kiểm tra chất lượng dữ liệu</a>\n                            <a href="/dieu-tra" data-batch-template="/dieu-tra/{batch_id}/tien-do" role="menuitem">2.3.2. Theo dõi tiến độ</a>\n                            <a href="/dieu-tra" data-batch-template="/dieu-tra/{batch_id}/bao-cao-tong-hop" role="menuitem">2.3.3. Báo cáo tổng hợp đợt</a>\n                            {% if menu_role != \'GIAO_VIEN\' %}\n                                <a href="/dieu-tra" data-batch-template="/dieu-tra/{batch_id}/chot-so-lieu" role="menuitem">2.3.4. Chốt / mở số liệu</a>\n                                <a href="/dieu-tra" data-batch-template="/dieu-tra/{batch_id}/bang-dieu-hanh-dia-ban" role="menuitem">2.3.5. Bảng điều hành địa bàn</a>\n                            {% endif %}\n                        </div>\n                    </div>\n\n                    {% if menu_role in [\'ADMIN\', \'SO\', \'PHONG_BAN\', \'XA\', \'TRUONG\'] %}\n                    <div class="pc-submenu">\n                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                            <span class="pc-submenu-trigger__text">2.4. Kế thừa và liên năm</span>\n                            <span class="pc-submenu-arrow">▶</span>\n                        </button>\n                        <div class="pc-submenu-panel" role="menu">\n                            <a href="/dieu-tra" data-batch-template="/dieu-tra/{batch_id}/ke-thua-du-lieu" role="menuitem">2.4.1. Kế thừa dữ liệu năm trước</a>\n                            <a href="/dieu-tra" data-batch-template="/dieu-tra/{batch_id}/doi-chieu-nam-hoc" role="menuitem">2.4.2. Đối chiếu giữa các năm học</a>\n                            <a href="/dieu-tra" data-batch-template="/dieu-tra/{batch_id}/xu-huong-lien-nam" role="menuitem">2.4.3. Xu hướng liên năm</a>\n                        </div>\n                    </div>\n                    {% endif %}\n\n                    {% if menu_role in [\'ADMIN\', \'SO\', \'PHONG_BAN\', \'XA\', \'TRUONG\'] %}\n                    <div class="pc-submenu">\n                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                            <span class="pc-submenu-trigger__text">2.5. Đối chiếu dữ liệu học sinh</span>\n                            <span class="pc-submenu-arrow">▶</span>\n                        </button>\n                        <div class="pc-submenu-panel" role="menu">\n                            <a href="/dieu-tra" data-batch-template="/dieu-tra/{batch_id}/doi-chieu-hoc-sinh" role="menuitem">2.5.1. Đối chiếu điều tra với học sinh</a>\n                            <a href="/dieu-tra" data-batch-template="/dieu-tra/{batch_id}/doi-chieu-hoc-sinh/chot-ket-qua" role="menuitem">2.5.2. Chốt / mở kết quả đối chiếu</a>\n                            {% if menu_role in [\'ADMIN\', \'SO\', \'PHONG_BAN\'] %}\n                                <a href="/dieu-tra/tong-hop-doi-chieu-hoc-sinh" role="menuitem">2.5.3. Tổng hợp chốt đối chiếu toàn tỉnh</a>\n                                <a href="/dieu-tra/don-doc-doi-chieu-hoc-sinh" role="menuitem">2.5.4. Giám sát tiến độ và nhắc việc</a>\n                            {% endif %}\n                        </div>\n                    </div>\n                    {% endif %}\n                </div>\n            </div>\n\n            {% if menu_role in [\'ADMIN\', \'SO\'] %}\n                <div class="pc-menu-group {% if menu_path.startswith(\'/hoc-sinh\') %}is-active{% endif %}">\n                    <button type="button" class="pc-menu-trigger" aria-expanded="false">\n                        3. Học sinh <span class="pc-menu-caret">▾</span>\n                    </button>\n                    <div class="pc-dropdown" role="menu">\n                        <div class="pc-submenu">\n                            <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                                <span class="pc-submenu-trigger__text">3.1. Hồ sơ học sinh</span>\n                                <span class="pc-submenu-arrow">▶</span>\n                            </button>\n                            <div class="pc-submenu-panel" role="menu">\n                                <a href="/hoc-sinh" role="menuitem">3.1.1. Danh sách học sinh</a>\n                                <a href="/hoc-sinh/them" role="menuitem">3.1.2. Thêm học sinh mới</a>\n                            </div>\n                        </div>\n                    </div>\n                </div>\n            {% endif %}\n\n            <div class="pc-menu-group {% if menu_path.startswith(\'/doi-ngu\') %}is-active{% endif %}">\n                <button type="button" class="pc-menu-trigger" aria-expanded="false">\n                    4. Đội ngũ <span class="pc-menu-caret">▾</span>\n                </button>\n                <div class="pc-dropdown" role="menu">\n                    <div class="pc-submenu">\n                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                            <span class="pc-submenu-trigger__text">4.1. Dữ liệu đội ngũ</span>\n                            <span class="pc-submenu-arrow">▶</span>\n                        </button>\n                        <div class="pc-submenu-panel" role="menu">\n                            <a href="/doi-ngu" role="menuitem">4.1.1. Danh sách đội ngũ</a>\n                            <a href="/doi-ngu/kiem-tra-du-lieu" role="menuitem">4.1.2. Kiểm tra dữ liệu đội ngũ</a>\n                            <a href="/doi-ngu/xuat-mau-excel" role="menuitem">4.1.3. Xuất mẫu Excel đội ngũ</a>\n                            <a href="/doi-ngu/xuat-danh-sach-excel" role="menuitem">4.1.4. Xuất danh sách Excel</a>\n                        </div>\n                    </div>\n\n                    {% if menu_role in [\'ADMIN\', \'SO\', \'TRUONG\'] %}\n                    <div class="pc-submenu">\n                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                            <span class="pc-submenu-trigger__text">4.2. Cập nhật đội ngũ</span>\n                            <span class="pc-submenu-arrow">▶</span>\n                        </button>\n                        <div class="pc-submenu-panel" role="menu">\n                            <a href="/doi-ngu/them" role="menuitem">4.2.1. Thêm nhân sự</a>\n                            <a href="/doi-ngu/cau-hinh-lop" role="menuitem">4.2.2. Cấu hình lớp</a>\n                        </div>\n                    </div>\n                    {% endif %}\n                </div>\n            </div>\n\n            <div class="pc-menu-group {% if menu_path.startswith(\'/bao-cao\') %}is-active{% endif %}">\n                <button type="button" class="pc-menu-trigger" aria-expanded="false">\n                    5. Báo cáo <span class="pc-menu-caret">▾</span>\n                </button>\n                <div class="pc-dropdown pc-dropdown--right" role="menu">\n                    <div class="pc-submenu">\n                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                            <span class="pc-submenu-trigger__text">5.1. Báo cáo chính</span>\n                            <span class="pc-submenu-arrow">▶</span>\n                        </button>\n                        <div class="pc-submenu-panel" role="menu">\n                            <a href="/bao-cao" role="menuitem">5.1.1. Trung tâm báo cáo</a>\n                            <a href="/bao-cao/tong-hop-dieu-tra" role="menuitem">5.1.2. Báo cáo tổng hợp điều tra</a>\n                            <a href="/bao-cao/pho-cap-3-5-tuoi" role="menuitem">5.1.3. Báo cáo trẻ 3–5 tuổi</a>\n                            <a href="/bao-cao/pcgdmn-mau-2025" role="menuitem">5.1.4. Biểu mẫu PCGDMN 2025</a>\n                            <a href="/bao-cao/bien-dong-theo-doi" role="menuitem">5.1.5. Biến động – theo dõi</a>\n                        </div>\n                    </div>\n\n                    <div class="pc-submenu">\n                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                            <span class="pc-submenu-trigger__text">5.2. Báo cáo giám sát</span>\n                            <span class="pc-submenu-arrow">▶</span>\n                        </button>\n                        <div class="pc-submenu-panel" role="menu">\n                            <a href="/bao-cao?report_type=DOI_CHIEU_HOC_SINH" role="menuitem">5.2.1. Báo cáo đối chiếu học sinh</a>\n                            <a href="/bao-cao?report_type=TIEN_DO_CHOT" role="menuitem">5.2.2. Báo cáo tiến độ – đôn đốc</a>\n                            {% if menu_role in [\'ADMIN\', \'SO\', \'PHONG_BAN\'] %}\n                                <a href="/dieu-tra/tong-hop-doi-chieu-hoc-sinh" role="menuitem">5.2.3. Tổng hợp đối chiếu toàn tỉnh</a>\n                                <a href="/dieu-tra/don-doc-doi-chieu-hoc-sinh" role="menuitem">5.2.4. Danh sách đôn đốc</a>\n                            {% endif %}\n                        </div>\n                    </div>\n                </div>\n            </div>\n        </div>\n    </nav>\n\n    <script>\n        (function () {\n            const nav = document.querySelector(\'[data-pc-dropdown-menu-v13]\');\n            if (!nav || nav.dataset.pcReady === \'1\') return;\n            nav.dataset.pcReady = \'1\';\n\n            const groups = Array.from(nav.querySelectorAll(\'.pc-menu-group\'));\n\n            function setExpanded(button, value) {\n                if (button) button.setAttribute(\'aria-expanded\', value ? \'true\' : \'false\');\n            }\n\n            function closeSubmenus(container) {\n                (container || nav).querySelectorAll(\'.pc-submenu.is-open\').forEach(function (submenu) {\n                    submenu.classList.remove(\'is-open\', \'opens-left\');\n                    setExpanded(submenu.querySelector(\':scope > .pc-submenu-trigger\'), false);\n                });\n            }\n\n            function closeGroup(group) {\n                if (!group) return;\n                group.classList.remove(\'is-open\');\n                setExpanded(group.querySelector(\':scope > .pc-menu-trigger\'), false);\n                closeSubmenus(group);\n            }\n\n            function closeAll(except) {\n                groups.forEach(function (group) {\n                    if (group !== except) closeGroup(group);\n                });\n            }\n\n            function fitSubmenu(submenu) {\n                const panel = submenu.querySelector(\':scope > .pc-submenu-panel\');\n                if (!panel || window.innerWidth <= 760) return;\n                submenu.classList.remove(\'opens-left\');\n                const rect = panel.getBoundingClientRect();\n                if (rect.right > window.innerWidth - 8) {\n                    submenu.classList.add(\'opens-left\');\n                }\n            }\n\n            function setupBatchLinks() {\n                const currentMatch = window.location.pathname.match(/^\\/dieu-tra\\/(\\d+)(?:\\/|$)/);\n                let batchId = currentMatch ? currentMatch[1] : \'\';\n\n                try {\n                    if (batchId) {\n                        window.localStorage.setItem(\'pc_last_survey_batch_id\', batchId);\n                    } else {\n                        batchId = window.localStorage.getItem(\'pc_last_survey_batch_id\') || \'\';\n                    }\n                } catch (error) {\n                    /* Trình duyệt chặn localStorage: chỉ dùng batch hiện tại nếu có. */\n                }\n\n                nav.querySelectorAll(\'[data-batch-template]\').forEach(function (link) {\n                    const template = link.getAttribute(\'data-batch-template\') || \'\';\n                    if (batchId) {\n                        link.setAttribute(\'href\', template.replace(\'{batch_id}\', batchId));\n                        link.classList.remove(\'pc-batch-link-needs-selection\');\n                        link.removeAttribute(\'title\');\n                    } else {\n                        link.setAttribute(\'href\', \'/dieu-tra\');\n                        link.classList.add(\'pc-batch-link-needs-selection\');\n                        link.setAttribute(\'title\', \'Hãy mở một đợt điều tra trước; hệ thống sẽ ghi nhớ đợt đang làm việc.\');\n                    }\n                });\n            }\n\n            groups.forEach(function (group) {\n                const trigger = group.querySelector(\':scope > .pc-menu-trigger\');\n                if (!trigger) return;\n\n                trigger.addEventListener(\'click\', function (event) {\n                    event.preventDefault();\n                    event.stopPropagation();\n                    const opening = !group.classList.contains(\'is-open\');\n                    closeAll(group);\n                    group.classList.toggle(\'is-open\', opening);\n                    setExpanded(trigger, opening);\n                    if (!opening) closeSubmenus(group);\n                });\n\n                group.addEventListener(\'mouseenter\', function () {\n                    if (!window.matchMedia(\'(hover: hover) and (pointer: fine)\').matches) return;\n                    closeAll(group);\n                    group.classList.add(\'is-open\');\n                    setExpanded(trigger, true);\n                });\n\n                group.addEventListener(\'mouseleave\', function () {\n                    if (!window.matchMedia(\'(hover: hover) and (pointer: fine)\').matches) return;\n                    closeGroup(group);\n                });\n\n                group.querySelectorAll(\'.pc-submenu\').forEach(function (submenu) {\n                    const subTrigger = submenu.querySelector(\':scope > .pc-submenu-trigger\');\n                    if (!subTrigger) return;\n\n                    subTrigger.addEventListener(\'click\', function (event) {\n                        event.preventDefault();\n                        event.stopPropagation();\n                        const opening = !submenu.classList.contains(\'is-open\');\n\n                        group.querySelectorAll(\'.pc-submenu.is-open\').forEach(function (other) {\n                            if (other !== submenu) {\n                                other.classList.remove(\'is-open\', \'opens-left\');\n                                setExpanded(other.querySelector(\':scope > .pc-submenu-trigger\'), false);\n                            }\n                        });\n\n                        submenu.classList.toggle(\'is-open\', opening);\n                        setExpanded(subTrigger, opening);\n\n                        if (opening) {\n                            requestAnimationFrame(function () {\n                                fitSubmenu(submenu);\n                            });\n                        } else {\n                            submenu.classList.remove(\'opens-left\');\n                        }\n                    });\n\n                    submenu.addEventListener(\'mouseenter\', function () {\n                        if (!window.matchMedia(\'(hover: hover) and (pointer: fine)\').matches) return;\n\n                        group.querySelectorAll(\'.pc-submenu.is-open\').forEach(function (other) {\n                            if (other !== submenu) {\n                                other.classList.remove(\'is-open\', \'opens-left\');\n                                setExpanded(other.querySelector(\':scope > .pc-submenu-trigger\'), false);\n                            }\n                        });\n\n                        submenu.classList.add(\'is-open\');\n                        setExpanded(subTrigger, true);\n\n                        requestAnimationFrame(function () {\n                            fitSubmenu(submenu);\n                        });\n                    });\n                });\n            });\n\n            document.addEventListener(\'click\', function (event) {\n                if (!nav.contains(event.target)) closeAll();\n            });\n\n            document.addEventListener(\'keydown\', function (event) {\n                if (event.key === \'Escape\') closeAll();\n            });\n\n            window.addEventListener(\'resize\', function () {\n                nav.querySelectorAll(\'.pc-submenu.opens-left\').forEach(function (submenu) {\n                    submenu.classList.remove(\'opens-left\');\n                });\n            });\n\n            setupBatchLinks();\n        }());\n    </script>\n{% endif %}\n'

def sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_with_parent(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def inject_include(text: str) -> tuple[str, bool]:
    if INCLUDE_MARKER in text:
        return text, False

    match = re.search(r"<body\b[^>]*>", text, flags=re.IGNORECASE)
    if match is None:
        raise RuntimeError("Khong tim thay the <body> trong template.")

    insert_at = match.end()
    addition = "\n" + INCLUDE_MARKER + "\n"
    return text[:insert_at] + addition + text[insert_at:], True


def main() -> int:
    project = PROJECT
    if len(sys.argv) >= 2:
        project = Path(sys.argv[1]).expanduser().resolve()

    templates_dir = project / "app" / "templates"
    partial_path = project / PARTIAL_REL
    main_py = project / MAIN_REL
    db_path = project / DB_REL

    print("\n" + "=" * 72)
    print("NANG CAP MENU SO XUONG V1.3 - DAY DU CHUC NANG")
    print("CHI DOI DIEU HUONG / HIEN THI - KHONG DOI ROUTE - KHONG DOI DU LIEU")
    print("=" * 72)

    if not templates_dir.exists():
        raise FileNotFoundError(f"Khong tim thay: {templates_dir}")
    if not main_py.exists():
        raise FileNotFoundError(f"Khong tim thay: {main_py}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = project / "exports" / f"backup_menu_so_xuong_v1_3_{stamp}"
    backup.mkdir(parents=True, exist_ok=False)

    main_hash_before = sha256(main_py)
    db_hash_before = sha256(db_path)

    html_files = sorted(templates_dir.rglob("*.html"))
    targets: list[Path] = []

    for file_path in html_files:
        rel = file_path.relative_to(templates_dir).as_posix()
        if rel in EXCLUDED_TEMPLATES or rel.startswith("partials/"):
            continue
        targets.append(file_path)

    print("\nBUOC 1 - SAO LUU AN TOAN")
    files_to_backup = [main_py, *targets]
    if partial_path.exists():
        files_to_backup.append(partial_path)
    if db_path.exists():
        files_to_backup.append(db_path)

    backed_up: list[str] = []
    for source in files_to_backup:
        rel = source.relative_to(project)
        copy_with_parent(source, backup / rel)
        backed_up.append(rel.as_posix())

    print(f"Ban sao an toan: {backup}")

    changed_files: list[str] = []
    created_files: list[str] = []

    try:
        print("\nBUOC 2 - CAP NHAT MENU DAY DU CHUC NANG")
        partial_path.parent.mkdir(parents=True, exist_ok=True)
        if not partial_path.exists():
            created_files.append(PARTIAL_REL.as_posix())

        partial_path.write_text(MENU_TEMPLATE, encoding="utf-8")
        changed_files.append(PARTIAL_REL.as_posix())

        print("Da cap nhat: app/templates/partials/dropdown_menu_v1.html")
        print("Da dua cac chuc nang truy cap nhanh len menu so xuong.")

        print("\nBUOC 3 - DAM BAO MENU XUAT HIEN TREN CAC GIAO DIEN CON")
        injected = 0
        already = 0

        for template_path in targets:
            rel = template_path.relative_to(project).as_posix()
            text = template_path.read_text(encoding="utf-8-sig")
            new_text, did_change = inject_include(text)

            if did_change:
                template_path.write_text(new_text, encoding="utf-8")
                changed_files.append(rel)
                injected += 1
            else:
                already += 1

        print(f"Da gan them menu vao {injected} template; {already} template da co menu.")

        print("\nBUOC 4 - KIEM TRA MENU VA JINJA")
        from jinja2 import Environment, FileSystemLoader

        env = Environment(loader=FileSystemLoader(str(templates_dir)))
        env.get_template("partials/dropdown_menu_v1.html")

        syntax_errors: list[str] = []
        missing_include: list[str] = []

        for template_path in targets:
            rel_t = template_path.relative_to(templates_dir).as_posix()
            text = template_path.read_text(encoding="utf-8-sig")

            try:
                env.parse(text)
            except Exception as exc:
                syntax_errors.append(f"{rel_t}: {exc}")

            if INCLUDE_MARKER not in text:
                missing_include.append(rel_t)

        if syntax_errors:
            raise RuntimeError(
                "Loi cu phap Jinja:\n" + "\n".join(syntax_errors[:12])
            )

        if missing_include:
            raise RuntimeError(
                "Template chua co menu:\n" + "\n".join(missing_include[:12])
            )

        required_menu_texts = [
            "Tài khoản Phòng ban",
            "Tài khoản Xã/phường",
            "Tài khoản Trường mầm non",
            "Cấp tài khoản đồng loạt",
            "Danh sách đợt điều tra",
            "Khởi tạo năm học toàn tỉnh",
            "Điều hành triển khai toàn tỉnh",
            "Trung tâm dữ liệu lịch sử",
            "Trung tâm phiếu điều tra",
            "Danh sách hộ dân",
            "In phiếu điều tra",
            "Xuất Excel điều tra",
            "Nhập Excel cập nhật hộ dân",
            "Phân công trường",
            "Giao phiếu cho trường",
            "Giao phiếu cho giáo viên",
            "Phân công hàng loạt",
            "Kiểm tra chất lượng dữ liệu",
            "Theo dõi tiến độ",
            "Báo cáo tổng hợp đợt",
            "Chốt / mở số liệu",
            "Bảng điều hành địa bàn",
            "Kế thừa dữ liệu năm trước",
            "Đối chiếu giữa các năm học",
            "Xu hướng liên năm",
            "Đối chiếu điều tra với học sinh",
            "Chốt / mở kết quả đối chiếu",
            "Tổng hợp chốt đối chiếu toàn tỉnh",
            "Giám sát tiến độ và nhắc việc",
            "Danh sách học sinh",
            "Thêm học sinh mới",
            "Danh sách đội ngũ",
            "Kiểm tra dữ liệu đội ngũ",
            "Xuất mẫu Excel đội ngũ",
            "Xuất danh sách Excel",
            "Thêm nhân sự",
            "Cấu hình lớp",
            "Trung tâm báo cáo",
            "Báo cáo tổng hợp điều tra",
            "Báo cáo trẻ 3–5 tuổi",
            "Biểu mẫu PCGDMN 2025",
            "Biến động – theo dõi",
            "Báo cáo đối chiếu học sinh",
            "Báo cáo tiến độ – đôn đốc",
        ]

        missing_items = [
            item for item in required_menu_texts
            if item not in MENU_TEMPLATE
        ]

        if missing_items:
            raise RuntimeError(
                "Menu V1.3 con thieu muc:\n" + "\n".join(missing_items)
            )

        if ".roles," not in MENU_TEMPLATE:
            raise RuntimeError("Chua an cac o chon o Trang chu.")
        if ".survey-menu-grid," not in MENU_TEMPLATE:
            raise RuntimeError("Chua an cac o chon o Quan ly dieu tra.")
        if ".quick-access-grid," not in MENU_TEMPLATE:
            raise RuntimeError("Chua an cac o chon o Quan ly tai khoan.")
        if ".catalog {" not in MENU_TEMPLATE:
            raise RuntimeError("Chua an cac o chon o Trung tam bao cao.")

        if sha256(main_py) != main_hash_before:
            raise RuntimeError("app/main.py da bi thay doi ngoai du kien.")

        if sha256(db_path) != db_hash_before:
            raise RuntimeError("data/phocap.db da bi thay doi ngoai du kien.")

        manifest = {
            "version": VERSION,
            "installed_at": datetime.now().isoformat(timespec="seconds"),
            "project": str(project),
            "backup": str(backup),
            "changed_files": sorted(set(changed_files)),
            "created_files": sorted(set(created_files)),
            "backed_up": sorted(set(backed_up)),
            "templates_with_menu": len(targets),
            "main_py_sha256_before": main_hash_before,
            "main_py_sha256_after": sha256(main_py),
            "database_sha256_before": db_hash_before,
            "database_sha256_after": sha256(db_path),
        }

        (backup / "MENU_V1_3_MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        latest = project / "exports" / "menu_so_xuong_v1_3_backup_moi_nhat.txt"
        latest.write_text(str(backup), encoding="utf-8")

        print("\nJinja: DAT")
        print("app/main.py: KHONG DOI")
        print("data/phocap.db: KHONG DOI")
        print("Route: KHONG DOI")
        print("Nghiep vu: KHONG DOI")
        print(f"So giao dien co menu: {len(targets)}")
        print("Cac o chon trung lap: DA AN")
        print("Menu theo dot: TU GHI NHO DOT DANG LAM VIEC")
        print("\n" + "=" * 72)
        print("NANG CAP MENU SO XUONG V1.3 THANH CONG")
        print("=" * 72)
        print(f"Ban sao an toan: {backup}")
        print("Khoi dong lai Uvicorn va nhan Ctrl+F5 tren trinh duyet.")
        return 0

    except Exception:
        print("\nNANG CAP KHONG THANH CONG - DANG TU DONG KHOI PHUC...")
        traceback.print_exc()

        for template_path in targets:
            rel = template_path.relative_to(project)
            saved = backup / rel
            if saved.exists():
                copy_with_parent(saved, template_path)

        saved_partial = backup / PARTIAL_REL
        if saved_partial.exists():
            copy_with_parent(saved_partial, partial_path)
        elif partial_path.exists():
            partial_path.unlink()

        print("DA KHOI PHUC CAC TEP GIAO DIEN CU.")
        print("app/main.py VA data/phocap.db KHONG BI GHI DE.")
        print(f"Ban sao an toan: {backup}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
