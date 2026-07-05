# -*- coding: utf-8 -*-
"""
通知推送配置
============
请填入你的 API Key / 邮箱密码后保存。

PushPlus (微信推送): https://www.pushplus.plus/ 注册获取 token
Email (SMTP): 使用 Outlook 邮箱的 应用专用密码，不是登录密码
"""

# ========== PushPlus 微信推送 ==========
PUSHPLUS_TOKEN = ""

# ========== 邮箱推送 ==========
SMTP_SERVER = "smtp.office365.com"
SMTP_PORT = 587
SMTP_USER = "rofist-1@outlook.com"
SMTP_PASS = ""  # 应用专用密码
EMAIL_TO = "rofist-1@outlook.com"

# ========== 推送开关 ==========
ENABLE_WECHAT = True
ENABLE_EMAIL = True

# ========== 日程 ==========
RUN_HOUR = 22
RUN_MINUTE = 0
