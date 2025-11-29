app_name = "inv_count"
app_title = "Inventory Count"
app_publisher = "Microtec"
app_description = "Inventory count"
app_email = "philippev@microtecinformatique.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "inv_count",
# 		"logo": "/assets/inv_count/logo.png",
# 		"title": "Inventory Count",
# 		"route": "/inv_count",
# 		"has_permission": "inv_count.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/inv_count/css/inv_count.css"
# app_include_js = "/assets/inv_count/js/inv_count.js"

# include js, css files in header of web template
# web_include_css = "/assets/inv_count/css/inv_count.css"
# web_include_js = "/assets/inv_count/js/inv_count.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "inv_count/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "inv_count/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "inv_count.utils.jinja_methods",
# 	"filters": "inv_count.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "inv_count.install.before_install"
# after_install = "inv_count.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "inv_count.uninstall.before_uninstall"
# after_uninstall = "inv_count.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "inv_count.utils.before_app_install"
# after_app_install = "inv_count.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "inv_count.utils.before_app_uninstall"
# after_app_uninstall = "inv_count.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "inv_count.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Inventory Count": {
		"on_update": "inv_count.inventory_count.doctype.inventory_count.inventory_count.on_update"
	}
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"inv_count.tasks.all"
# 	],
# 	"daily": [
# 		"inv_count.tasks.daily"
# 	],
# 	"hourly": [
# 		"inv_count.tasks.hourly"
# 	],
# 	"weekly": [
# 		"inv_count.tasks.weekly"
# 	],
# 	"monthly": [
# 		"inv_count.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "inv_count.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "inv_count.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "inv_count.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["inv_count.utils.before_request"]
# after_request = ["inv_count.utils.after_request"]

# Job Events
# ----------
# before_job = ["inv_count.utils.before_job"]
# after_job = ["inv_count.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"inv_count.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

