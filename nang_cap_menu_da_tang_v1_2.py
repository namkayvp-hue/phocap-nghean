from __future__ import annotations

import hashlib
import json
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
VERSION = "MENU-SO-XUONG-V1.2-DA-TANG"
PARTIAL_REL = Path("app/templates/partials/dropdown_menu_v1.html")
MAIN_REL = Path("app/main.py")
DB_REL = Path("data/phocap.db")

MENU_TEMPLATE = r'''{# ============================================================
   MENU SỔ XUỐNG V1.2 - ĐA TẦNG
   Mục tiêu:
   - Thanh menu dùng chung cho mọi giao diện con sau đăng nhập.
   - Menu cấp 1 xổ xuống; nhóm nghiệp vụ bên trong tiếp tục xổ ngang.
   - Chỉ điều hướng giao diện.
   - Không thay đổi route, dữ liệu hoặc nghiệp vụ.
   - Giữ nguyên các liên kết/route đã có trong Menu V1.
   ============================================================ #}
<style id="pc-menu-v12-inline-style">
.pc-global-nav,
.pc-global-nav * {
    box-sizing: border-box;
}

.pc-global-nav {
    position: sticky;
    top: 0;
    z-index: 5000;
    width: 100%;
    font-family: Arial, Helvetica, sans-serif;
    color: #ffffff;
    background: #ffffff;
    box-shadow: 0 3px 12px rgba(18, 52, 86, 0.18);
}

.pc-global-nav__top {
    min-height: 56px;
    padding: 7px max(18px, calc((100% - 1280px) / 2));
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
    background: linear-gradient(90deg, #0d47a1 0%, #1565c0 58%, #1976d2 100%);
}

.pc-global-nav__brand {
    min-width: 0;
    display: inline-flex;
    align-items: center;
    gap: 10px;
    color: #ffffff !important;
    text-decoration: none !important;
}

.pc-global-nav__brand-mark {
    width: 36px;
    height: 36px;
    flex: 0 0 36px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
    background: #ffffff;
    color: #0d47a1;
    font-size: 14px;
    font-weight: 800;
}

.pc-global-nav__brand-text {
    min-width: 0;
    display: flex;
    flex-direction: column;
    line-height: 1.15;
}

.pc-global-nav__brand-text strong {
    color: #ffffff;
    font-size: 14px;
    letter-spacing: .25px;
    white-space: nowrap;
}

.pc-global-nav__brand-text small {
    margin-top: 3px;
    color: rgba(255,255,255,.9);
    font-size: 11px;
}

.pc-global-nav__account {
    display: grid;
    grid-template-columns: minmax(0, auto) auto;
    grid-template-areas: "name logout" "unit logout";
    align-items: center;
    column-gap: 12px;
    text-align: right;
}

.pc-global-nav__account-name {
    grid-area: name;
    color: #ffffff;
    font-size: 14px;
    font-weight: 700;
}

.pc-global-nav__account-unit {
    grid-area: unit;
    max-width: 460px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: rgba(255,255,255,.9);
    font-size: 11px;
}

.pc-global-nav__logout-form {
    grid-area: logout;
    margin: 0 !important;
}

.pc-global-nav__logout {
    min-height: 34px;
    padding: 7px 12px;
    border: 1px solid rgba(255,255,255,.62);
    border-radius: 7px;
    background: rgba(255,255,255,.12);
    color: #ffffff;
    font: inherit;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
}

.pc-global-nav__logout:hover,
.pc-global-nav__logout:focus-visible {
    background: #ffffff;
    color: #0d47a1;
    outline: none;
}

.pc-global-nav__bar {
    min-height: 43px;
    padding: 0 max(18px, calc((100% - 1280px) / 2));
    display: flex;
    align-items: stretch;
    gap: 0;
    background: #ffffff;
    border-bottom: 1px solid #d8e1eb;
    color: #25364a;
    overflow: visible;
}

.pc-global-nav__home,
.pc-menu-trigger {
    min-height: 43px;
    margin: 0;
    padding: 0 15px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    border: 0;
    border-right: 1px solid #e5ebf1;
    border-radius: 0;
    background: transparent;
    color: #25364a !important;
    font: inherit;
    font-size: 14px;
    font-weight: 600;
    line-height: 1.2;
    text-decoration: none !important;
    white-space: nowrap;
    cursor: pointer;
    box-shadow: none;
}

.pc-global-nav__home:hover,
.pc-global-nav__home:focus-visible,
.pc-menu-trigger:hover,
.pc-menu-trigger:focus-visible,
.pc-menu-group.is-open > .pc-menu-trigger,
.pc-menu-group.is-active > .pc-menu-trigger,
.pc-global-nav__home.is-active {
    background: #eaf3ff;
    color: #0d5fb8 !important;
    outline: none;
}

.pc-menu-group {
    position: relative;
    display: flex;
    align-items: stretch;
}

.pc-menu-caret {
    font-size: 11px;
    transition: transform .16s ease;
}

.pc-menu-group.is-open > .pc-menu-trigger .pc-menu-caret {
    transform: rotate(180deg);
}

.pc-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    z-index: 5100;
    width: max-content;
    min-width: 300px;
    max-width: min(430px, calc(100vw - 28px));
    padding: 6px 0;
    display: none;
    background: #ffffff;
    border: 1px solid #d9e2ec;
    border-radius: 0 0 8px 8px;
    box-shadow: 0 12px 28px rgba(30,53,79,.18);
}

.pc-menu-group.is-open > .pc-dropdown,
.pc-menu-group:focus-within > .pc-dropdown {
    display: block;
}

.pc-dropdown--right {
    left: auto;
    right: 0;
}

.pc-dropdown > a,
.pc-submenu-trigger,
.pc-submenu-panel > a {
    width: 100%;
    min-height: 39px;
    margin: 0;
    padding: 9px 14px;
    display: flex;
    align-items: center;
    gap: 10px;
    border: 0;
    border-radius: 0;
    background: #ffffff;
    color: #26384d !important;
    font: inherit;
    font-size: 13px;
    font-weight: 500;
    line-height: 1.35;
    text-align: left;
    text-decoration: none !important;
    white-space: normal;
    cursor: pointer;
}

.pc-dropdown > a:hover,
.pc-dropdown > a:focus-visible,
.pc-submenu-trigger:hover,
.pc-submenu-trigger:focus-visible,
.pc-submenu.is-open > .pc-submenu-trigger,
.pc-submenu:focus-within > .pc-submenu-trigger,
.pc-submenu-panel > a:hover,
.pc-submenu-panel > a:focus-visible {
    background: #eaf3ff;
    color: #0d5fb8 !important;
    outline: none;
}

.pc-submenu {
    position: relative;
}

.pc-submenu-trigger {
    justify-content: space-between;
    font-weight: 600;
}

.pc-submenu-trigger__text {
    min-width: 0;
    display: inline-flex;
    align-items: center;
    gap: 8px;
}

.pc-submenu-arrow {
    flex: 0 0 auto;
    color: #708196;
    font-size: 12px;
    line-height: 1;
}

.pc-submenu-panel {
    position: absolute;
    top: -7px;
    left: calc(100% - 2px);
    z-index: 5200;
    width: max-content;
    min-width: 315px;
    max-width: min(430px, calc(100vw - 28px));
    padding: 6px 0;
    display: none;
    background: #ffffff;
    border: 1px solid #d9e2ec;
    border-radius: 7px;
    box-shadow: 0 12px 28px rgba(30,53,79,.18);
}

.pc-submenu.is-open > .pc-submenu-panel,
.pc-submenu:focus-within > .pc-submenu-panel {
    display: block;
}

.pc-submenu.opens-left > .pc-submenu-panel,
.pc-dropdown--right .pc-submenu > .pc-submenu-panel {
    right: calc(100% - 2px);
    left: auto;
}

.pc-dropdown__section-title {
    padding: 7px 14px 6px;
    color: #8190a1;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: .45px;
    text-transform: uppercase;
}

.pc-dropdown__divider {
    height: 1px;
    margin: 5px 10px;
    background: #e8edf3;
}

.pc-dropdown__note {
    margin: 5px 10px;
    padding: 9px 10px;
    display: block;
    border-radius: 6px;
    background: #f5f8fb;
    color: #617286;
    font-size: 12px;
    line-height: 1.45;
}

.pc-submenu-panel .pc-dropdown__note {
    margin: 5px 10px;
}

@media (hover: hover) and (pointer: fine) {
    .pc-submenu:hover > .pc-submenu-panel {
        display: block;
    }

    .pc-submenu:hover > .pc-submenu-trigger {
        background: #eaf3ff;
        color: #0d5fb8 !important;
    }
}

@media (max-width: 1100px) {
    .pc-global-nav__account-unit {
        max-width: 260px;
    }

    .pc-global-nav__bar {
        padding-inline: 8px;
    }

    .pc-global-nav__home,
    .pc-menu-trigger {
        padding-inline: 11px;
    }
}

@media (max-width: 760px) {
    .pc-global-nav {
        position: relative;
    }

    .pc-global-nav__top {
        flex-direction: column;
        align-items: stretch;
        gap: 8px;
    }

    .pc-global-nav__brand-text strong {
        white-space: normal;
    }

    .pc-global-nav__account {
        grid-template-columns: 1fr auto;
        text-align: left;
    }

    .pc-global-nav__account-unit {
        max-width: 100%;
    }

    .pc-global-nav__bar {
        flex-wrap: wrap;
        overflow: visible;
        padding: 4px 8px;
    }

    .pc-global-nav__home,
    .pc-menu-trigger {
        min-height: 40px;
        border-right: 0;
        border-radius: 6px;
    }

    .pc-dropdown,
    .pc-dropdown--right {
        position: fixed;
        top: 105px;
        right: 10px;
        left: 10px;
        width: auto;
        max-width: none;
        max-height: calc(100vh - 120px);
        overflow-y: auto;
        border-radius: 8px;
    }

    .pc-submenu-panel,
    .pc-submenu.opens-left > .pc-submenu-panel,
    .pc-dropdown--right .pc-submenu > .pc-submenu-panel {
        position: static;
        width: auto;
        min-width: 0;
        max-width: none;
        margin: 0 8px 6px 18px;
        padding: 3px 0;
        border: 0;
        border-left: 3px solid #d6e7fb;
        border-radius: 0;
        box-shadow: none;
    }

    .pc-submenu-panel > a {
        min-height: 36px;
        padding-left: 13px;
        font-size: 12.5px;
    }

    .pc-submenu-arrow {
        transform: rotate(90deg);
    }
}

@media print {
    .pc-global-nav {
        display: none !important;
    }
}
</style>

{% set menu_user = nguoi_dung if nguoi_dung is defined and nguoi_dung else (request.scope.get('auth_user') if request is defined else none) %}
{% if menu_user %}
    {% set menu_role = (menu_user.role_code or '')|upper %}
    {% set menu_path = request.url.path if request is defined else '/' %}

    <nav class="pc-global-nav" aria-label="Điều hướng chính">
        <div class="pc-global-nav__top">
            <a class="pc-global-nav__brand" href="/" title="Về trang chủ">
                <span class="pc-global-nav__brand-mark">PC</span>
                <span class="pc-global-nav__brand-text">
                    <strong>PHỔ CẬP GIÁO DỤC MẦM NON</strong>
                    <small>Hệ thống quản lý dữ liệu</small>
                </span>
            </a>

            <div class="pc-global-nav__account">
                <span class="pc-global-nav__account-name">{{ menu_user.full_name }}</span>
                <span class="pc-global-nav__account-unit">{{ menu_user.role_name }} · {{ menu_user.unit_name }}</span>
                <form method="post" action="/dang-xuat" class="pc-global-nav__logout-form">
                    <button type="submit" class="pc-global-nav__logout">Đăng xuất</button>
                </form>
            </div>
        </div>

        <div class="pc-global-nav__bar" data-pc-dropdown-menu-v12>
            <a class="pc-global-nav__home {% if menu_path == '/' %}is-active{% endif %}" href="/">
                Trang chủ
            </a>

            {% if menu_role in ['ADMIN', 'SO'] %}
                <div class="pc-menu-group {% if menu_path.startswith('/tai-khoan') or menu_path.startswith('/xa') or menu_path.startswith('/truong') %}is-active{% endif %}">
                    <button type="button" class="pc-menu-trigger" aria-expanded="false">
                        1. Danh mục <span class="pc-menu-caret">▾</span>
                    </button>
                    <div class="pc-dropdown" role="menu">
                        <div class="pc-submenu">
                            <button type="button" class="pc-submenu-trigger" aria-expanded="false">
                                <span class="pc-submenu-trigger__text">Quản lý tài khoản</span>
                                <span class="pc-submenu-arrow">▶</span>
                            </button>
                            <div class="pc-submenu-panel" role="menu">
                                <a href="/tai-khoan" role="menuitem">1.1. Quản lý tài khoản</a>
                            </div>
                        </div>
                        <div class="pc-submenu">
                            <button type="button" class="pc-submenu-trigger" aria-expanded="false">
                                <span class="pc-submenu-trigger__text">Đơn vị hành chính</span>
                                <span class="pc-submenu-arrow">▶</span>
                            </button>
                            <div class="pc-submenu-panel" role="menu">
                                <a href="/xa" role="menuitem">1.2. Danh mục xã/phường</a>
                                <a href="/truong" role="menuitem">1.3. Danh mục trường</a>
                            </div>
                        </div>
                    </div>
                </div>
            {% elif menu_role == 'XA' %}
                <div class="pc-menu-group {% if menu_path.startswith('/truong') %}is-active{% endif %}">
                    <button type="button" class="pc-menu-trigger" aria-expanded="false">
                        1. Danh mục <span class="pc-menu-caret">▾</span>
                    </button>
                    <div class="pc-dropdown" role="menu">
                        <div class="pc-submenu">
                            <button type="button" class="pc-submenu-trigger" aria-expanded="false">
                                <span class="pc-submenu-trigger__text">Trường thuộc địa bàn</span>
                                <span class="pc-submenu-arrow">▶</span>
                            </button>
                            <div class="pc-submenu-panel" role="menu">
                                <a href="/truong" role="menuitem">1.1. Trường thuộc xã/phường</a>
                            </div>
                        </div>
                    </div>
                </div>
            {% elif menu_role == 'TRUONG' %}
                <div class="pc-menu-group {% if menu_path.startswith('/tai-khoan') %}is-active{% endif %}">
                    <button type="button" class="pc-menu-trigger" aria-expanded="false">
                        1. Danh mục <span class="pc-menu-caret">▾</span>
                    </button>
                    <div class="pc-dropdown" role="menu">
                        <div class="pc-submenu">
                            <button type="button" class="pc-submenu-trigger" aria-expanded="false">
                                <span class="pc-submenu-trigger__text">Tài khoản giáo viên</span>
                                <span class="pc-submenu-arrow">▶</span>
                            </button>
                            <div class="pc-submenu-panel" role="menu">
                                <a href="/tai-khoan" role="menuitem">1.1. Tài khoản giáo viên</a>
                            </div>
                        </div>
                    </div>
                </div>
            {% endif %}

            <div class="pc-menu-group {% if menu_path.startswith('/dieu-tra') %}is-active{% endif %}">
                <button type="button" class="pc-menu-trigger" aria-expanded="false">
                    2. Điều tra hộ dân <span class="pc-menu-caret">▾</span>
                </button>
                <div class="pc-dropdown" role="menu">
                    {% if menu_role in ['ADMIN', 'SO'] %}
                        <div class="pc-submenu">
                            <button type="button" class="pc-submenu-trigger" aria-expanded="false">
                                <span class="pc-submenu-trigger__text">Đợt điều tra</span>
                                <span class="pc-submenu-arrow">▶</span>
                            </button>
                            <div class="pc-submenu-panel" role="menu">
                                <a href="/dieu-tra" role="menuitem">2.1. Danh sách đợt điều tra</a>
                                <a href="/dieu-tra/khoi-tao-nam-hoc-toan-tinh" role="menuitem">2.2. Khởi tạo năm học toàn tỉnh</a>
                                <a href="/dieu-tra/dieu-hanh-trien-khai" role="menuitem">2.3. Điều hành triển khai</a>
                            </div>
                        </div>
                        <div class="pc-submenu">
                            <button type="button" class="pc-submenu-trigger" aria-expanded="false">
                                <span class="pc-submenu-trigger__text">Phiếu và dữ liệu điều tra</span>
                                <span class="pc-submenu-arrow">▶</span>
                            </button>
                            <div class="pc-submenu-panel" role="menu">
                                <a href="/dieu-tra/trung-tam-phieu" role="menuitem">2.4. Trung tâm phiếu điều tra</a>
                                <a href="/dieu-tra/du-lieu-lich-su" role="menuitem">2.5. Dữ liệu lịch sử</a>
                            </div>
                        </div>
                        <div class="pc-submenu">
                            <button type="button" class="pc-submenu-trigger" aria-expanded="false">
                                <span class="pc-submenu-trigger__text">Đối chiếu dữ liệu học sinh</span>
                                <span class="pc-submenu-arrow">▶</span>
                            </button>
                            <div class="pc-submenu-panel" role="menu">
                                <a href="/dieu-tra/tong-hop-doi-chieu-hoc-sinh" role="menuitem">2.6. Tổng hợp đối chiếu học sinh</a>
                                <a href="/dieu-tra/don-doc-doi-chieu-hoc-sinh" role="menuitem">2.7. Theo dõi/đôn đốc đối chiếu</a>
                            </div>
                        </div>
                    {% elif menu_role == 'PHONG_BAN' %}
                        <a href="/dieu-tra" role="menuitem">2.1. Danh sách đợt điều tra</a>
                        <div class="pc-submenu">
                            <button type="button" class="pc-submenu-trigger" aria-expanded="false">
                                <span class="pc-submenu-trigger__text">Đối chiếu dữ liệu học sinh</span>
                                <span class="pc-submenu-arrow">▶</span>
                            </button>
                            <div class="pc-submenu-panel" role="menu">
                                <a href="/dieu-tra/tong-hop-doi-chieu-hoc-sinh" role="menuitem">2.2. Tổng hợp đối chiếu học sinh</a>
                                <a href="/dieu-tra/don-doc-doi-chieu-hoc-sinh" role="menuitem">2.3. Theo dõi/đôn đốc đối chiếu</a>
                            </div>
                        </div>
                    {% elif menu_role == 'XA' %}
                        <div class="pc-submenu">
                            <button type="button" class="pc-submenu-trigger" aria-expanded="false">
                                <span class="pc-submenu-trigger__text">Đợt điều tra được giao</span>
                                <span class="pc-submenu-arrow">▶</span>
                            </button>
                            <div class="pc-submenu-panel" role="menu">
                                <a href="/dieu-tra" role="menuitem">2.1. Danh sách đợt điều tra</a>
                                <span class="pc-dropdown__note">Phân công trường, khóa/mở và theo dõi tiến độ thực hiện trong từng đợt.</span>
                            </div>
                        </div>
                    {% elif menu_role == 'TRUONG' %}
                        <div class="pc-submenu">
                            <button type="button" class="pc-submenu-trigger" aria-expanded="false">
                                <span class="pc-submenu-trigger__text">Đợt điều tra được giao</span>
                                <span class="pc-submenu-arrow">▶</span>
                            </button>
                            <div class="pc-submenu-panel" role="menu">
                                <a href="/dieu-tra" role="menuitem">2.1. Danh sách đợt điều tra</a>
                                <span class="pc-dropdown__note">Phân công giáo viên và xử lý phiếu thực hiện trong từng đợt.</span>
                            </div>
                        </div>
                    {% else %}
                        <div class="pc-submenu">
                            <button type="button" class="pc-submenu-trigger" aria-expanded="false">
                                <span class="pc-submenu-trigger__text">Nhiệm vụ điều tra</span>
                                <span class="pc-submenu-arrow">▶</span>
                            </button>
                            <div class="pc-submenu-panel" role="menu">
                                <a href="/dieu-tra" role="menuitem">2.1. Danh sách đợt điều tra</a>
                                <span class="pc-dropdown__note">Mở đợt được giao để nhập và cập nhật các phiếu của bạn.</span>
                            </div>
                        </div>
                    {% endif %}
                </div>
            </div>

            {% if menu_role in ['ADMIN', 'SO'] %}
                <div class="pc-menu-group {% if menu_path.startswith('/hoc-sinh') %}is-active{% endif %}">
                    <button type="button" class="pc-menu-trigger" aria-expanded="false">
                        3. Học sinh <span class="pc-menu-caret">▾</span>
                    </button>
                    <div class="pc-dropdown" role="menu">
                        <div class="pc-submenu">
                            <button type="button" class="pc-submenu-trigger" aria-expanded="false">
                                <span class="pc-submenu-trigger__text">Hồ sơ học sinh</span>
                                <span class="pc-submenu-arrow">▶</span>
                            </button>
                            <div class="pc-submenu-panel" role="menu">
                                <a href="/hoc-sinh" role="menuitem">3.1. Danh sách học sinh</a>
                            </div>
                        </div>
                    </div>
                </div>
            {% endif %}

            <div class="pc-menu-group {% if menu_path.startswith('/doi-ngu') %}is-active{% endif %}">
                <button type="button" class="pc-menu-trigger" aria-expanded="false">
                    4. Đội ngũ <span class="pc-menu-caret">▾</span>
                </button>
                <div class="pc-dropdown" role="menu">
                    <div class="pc-submenu">
                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">
                            <span class="pc-submenu-trigger__text">Quản lý đội ngũ</span>
                            <span class="pc-submenu-arrow">▶</span>
                        </button>
                        <div class="pc-submenu-panel" role="menu">
                            <a href="/doi-ngu" role="menuitem">4.1. Danh sách đội ngũ</a>
                            {% if menu_role in ['ADMIN', 'SO', 'TRUONG'] %}
                                <a href="/doi-ngu/cau-hinh-lop" role="menuitem">4.2. Cấu hình lớp</a>
                            {% endif %}
                        </div>
                    </div>
                </div>
            </div>

            <div class="pc-menu-group {% if menu_path.startswith('/bao-cao') %}is-active{% endif %}">
                <button type="button" class="pc-menu-trigger" aria-expanded="false">
                    5. Báo cáo <span class="pc-menu-caret">▾</span>
                </button>
                <div class="pc-dropdown pc-dropdown--right" role="menu">
                    <div class="pc-submenu">
                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">
                            <span class="pc-submenu-trigger__text">Báo cáo và theo dõi</span>
                            <span class="pc-submenu-arrow">▶</span>
                        </button>
                        <div class="pc-submenu-panel" role="menu">
                            <a href="/bao-cao" role="menuitem">5.1. Trung tâm báo cáo</a>
                            <a href="/bao-cao/bien-dong-theo-doi" role="menuitem">5.2. Theo dõi biến động</a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </nav>

    <script>
        (function () {
            const nav = document.querySelector('[data-pc-dropdown-menu-v12]');
            if (!nav || nav.dataset.pcReady === '1') return;
            nav.dataset.pcReady = '1';

            const groups = Array.from(nav.querySelectorAll('.pc-menu-group'));

            function setExpanded(button, value) {
                if (button) button.setAttribute('aria-expanded', value ? 'true' : 'false');
            }

            function closeSubmenus(container) {
                (container || nav).querySelectorAll('.pc-submenu.is-open').forEach(function (submenu) {
                    submenu.classList.remove('is-open', 'opens-left');
                    setExpanded(submenu.querySelector(':scope > .pc-submenu-trigger'), false);
                });
            }

            function closeGroup(group) {
                if (!group) return;
                group.classList.remove('is-open');
                setExpanded(group.querySelector(':scope > .pc-menu-trigger'), false);
                closeSubmenus(group);
            }

            function closeAll(except) {
                groups.forEach(function (group) {
                    if (group !== except) closeGroup(group);
                });
            }

            function fitSubmenu(submenu) {
                const panel = submenu.querySelector(':scope > .pc-submenu-panel');
                if (!panel || window.innerWidth <= 760) return;
                submenu.classList.remove('opens-left');
                const rect = panel.getBoundingClientRect();
                if (rect.right > window.innerWidth - 8) {
                    submenu.classList.add('opens-left');
                }
            }

            groups.forEach(function (group) {
                const trigger = group.querySelector(':scope > .pc-menu-trigger');
                if (!trigger) return;

                trigger.addEventListener('click', function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    const opening = !group.classList.contains('is-open');
                    closeAll(group);
                    group.classList.toggle('is-open', opening);
                    setExpanded(trigger, opening);
                    if (!opening) closeSubmenus(group);
                });

                group.addEventListener('mouseenter', function () {
                    if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;
                    closeAll(group);
                    group.classList.add('is-open');
                    setExpanded(trigger, true);
                });

                group.addEventListener('mouseleave', function () {
                    if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;
                    closeGroup(group);
                });

                group.querySelectorAll('.pc-submenu').forEach(function (submenu) {
                    const subTrigger = submenu.querySelector(':scope > .pc-submenu-trigger');
                    if (!subTrigger) return;

                    subTrigger.addEventListener('click', function (event) {
                        event.preventDefault();
                        event.stopPropagation();
                        const opening = !submenu.classList.contains('is-open');
                        group.querySelectorAll('.pc-submenu.is-open').forEach(function (other) {
                            if (other !== submenu) {
                                other.classList.remove('is-open', 'opens-left');
                                setExpanded(other.querySelector(':scope > .pc-submenu-trigger'), false);
                            }
                        });
                        submenu.classList.toggle('is-open', opening);
                        setExpanded(subTrigger, opening);
                        if (opening) {
                            requestAnimationFrame(function () { fitSubmenu(submenu); });
                        } else {
                            submenu.classList.remove('opens-left');
                        }
                    });

                    submenu.addEventListener('mouseenter', function () {
                        if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;
                        group.querySelectorAll('.pc-submenu.is-open').forEach(function (other) {
                            if (other !== submenu) {
                                other.classList.remove('is-open', 'opens-left');
                                setExpanded(other.querySelector(':scope > .pc-submenu-trigger'), false);
                            }
                        });
                        submenu.classList.add('is-open');
                        setExpanded(subTrigger, true);
                        requestAnimationFrame(function () { fitSubmenu(submenu); });
                    });
                });
            });

            document.addEventListener('click', function (event) {
                if (!nav.contains(event.target)) closeAll();
            });

            document.addEventListener('keydown', function (event) {
                if (event.key === 'Escape') closeAll();
            });

            window.addEventListener('resize', function () {
                nav.querySelectorAll('.pc-submenu.opens-left').forEach(function (submenu) {
                    submenu.classList.remove('opens-left');
                });
            });
        }());
    </script>
{% endif %}
'''


def sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_with_parent(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def main() -> int:
    project = PROJECT
    if len(sys.argv) >= 2:
        project = Path(sys.argv[1]).expanduser().resolve()

    partial = project / PARTIAL_REL
    main_py = project / MAIN_REL
    db_path = project / DB_REL
    templates_dir = project / "app" / "templates"

    print("\n" + "=" * 76)
    print("NANG CAP MENU SO XUONG V1.2 - MENU DA TANG CHO CAC GIAO DIEN CON")
    print("CHI DOI DIEU HUONG - KHONG DOI ROUTE - KHONG DOI DU LIEU - KHONG DOI NGHIEP VU")
    print("=" * 76)

    for required in [partial, main_py, templates_dir]:
        if not required.exists():
            raise FileNotFoundError(f"Khong tim thay: {required}")

    main_hash_before = sha256(main_py)
    db_hash_before = sha256(db_path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = project / "exports" / f"backup_menu_so_xuong_v1_2_{stamp}"
    backup.mkdir(parents=True, exist_ok=False)

    try:
        print("\nBUOC 1 - SAO LUU AN TOAN MENU HIEN TAI")
        copy_with_parent(partial, backup / PARTIAL_REL)
        print(f"Ban sao an toan: {backup}")

        print("\nBUOC 2 - NANG CAP MENU CAP 1 + MENU CON XỔ NGANG")
        partial.write_text(MENU_TEMPLATE, encoding="utf-8")
        print("Da cap nhat: app/templates/partials/dropdown_menu_v1.html")

        print("\nBUOC 3 - KIEM TRA JINJA VA PHAM VI THAY DOI")
        from jinja2 import Environment, FileSystemLoader

        env = Environment(loader=FileSystemLoader(str(templates_dir)))
        env.get_template("partials/dropdown_menu_v1.html")

        syntax_errors: list[str] = []
        included_templates = 0
        include_marker = '{% include "partials/dropdown_menu_v1.html" %}'
        for template_path in sorted(templates_dir.rglob("*.html")):
            rel = template_path.relative_to(templates_dir).as_posix()
            try:
                env.parse(template_path.read_text(encoding="utf-8-sig"))
            except Exception as exc:
                syntax_errors.append(f"{rel}: {exc}")
            try:
                if include_marker in template_path.read_text(encoding="utf-8-sig"):
                    included_templates += 1
            except Exception:
                pass

        if syntax_errors:
            raise RuntimeError("Loi cu phap Jinja:\n" + "\n".join(syntax_errors[:12]))

        final = partial.read_text(encoding="utf-8-sig")
        checks = {
            "CSS V1.2": 'id="pc-menu-v12-inline-style"' in final,
            "Menu cap 2": "pc-submenu" in final,
            "Menu cap 3/xo ngang": "pc-submenu-panel" in final,
            "JS da tang": "data-pc-dropdown-menu-v12" in final,
            "Route cu /dieu-tra": 'href="/dieu-tra"' in final,
            "Route cu /tai-khoan": 'href="/tai-khoan"' in final,
            "Route cu /bao-cao": 'href="/bao-cao"' in final,
        }
        failed = [name for name, ok in checks.items() if not ok]
        if failed:
            raise RuntimeError("Kiem tra menu V1.2 khong dat: " + ", ".join(failed))

        if sha256(main_py) != main_hash_before:
            raise RuntimeError("app/main.py da bi thay doi - dung cai dat")
        if sha256(db_path) != db_hash_before:
            raise RuntimeError("data/phocap.db da bi thay doi - dung cai dat")

        manifest = {
            "version": VERSION,
            "installed_at": datetime.now().isoformat(timespec="seconds"),
            "project": str(project),
            "backup": str(backup),
            "changed_files": [PARTIAL_REL.as_posix()],
            "main_py_sha256_before": main_hash_before,
            "main_py_sha256_after": sha256(main_py),
            "database_sha256_before": db_hash_before,
            "database_sha256_after": sha256(db_path),
            "templates_with_global_menu": included_templates,
        }
        (backup / "MENU_V1_2_MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        latest = project / "exports" / "menu_so_xuong_v1_2_backup_moi_nhat.txt"
        latest.write_text(str(backup), encoding="utf-8")

        print("Jinja: DAT")
        print(f"So giao dien dang dung menu chung: {included_templates}")
        print("app/main.py: KHONG DOI")
        print("data/phocap.db: KHONG DOI")
        print("Route: KHONG DOI")
        print("Nghiep vu: KHONG DOI")
        print("Menu con: DA CHUYEN SANG KIEU XO NGANG NHIEU TANG")
        print("\n" + "=" * 76)
        print("NANG CAP MENU SO XUONG V1.2 THANH CONG")
        print("=" * 76)
        print(f"Ban sao an toan: {backup}")
        print("Khoi dong lai Uvicorn va nhan Ctrl+F5 tren trinh duyet.")
        return 0

    except Exception:
        print("\nNANG CAP KHONG THANH CONG - DANG TU DONG KHOI PHUC MENU V1.1...")
        traceback.print_exc()
        saved = backup / PARTIAL_REL
        if saved.exists():
            copy_with_parent(saved, partial)
        print("DA KHOI PHUC MENU TRUOC KHI NANG CAP.")
        print("app/main.py va data/phocap.db KHONG BI GHI DE.")
        print(f"Ban sao an toan: {backup}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
