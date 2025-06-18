# -*- coding: utf-8 -*-
#################################################################################
# Author      : Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# Copyright(c): 2015-Present Webkul Software Pvt. Ltd.
# All Rights Reserved.
#
#
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#
# You should have received a copy of the License along with this program.
# If not, see <https://store.webkul.com/license.html/>
#################################################################################
{
  "name"                 :  "Web: Odoo Debug Mode",
  "summary"              :  """Web: Odoo Debug Mode allows you to enable debug mode with just a click.""",
  "category"             :  "Extra Tools",
  "version"              :  "1.0.0",
  "author"               :  "Webkul Software Pvt. Ltd.",
  "maintainer"           :  "Prakash Kumar",
  "license"              :  "Other proprietary",
  "website"              :  "https://store.webkul.com/",
  "description"          :  """Web: Odoo Debug Mode
Odoo Debug Mode
Debug Mode
Enable Debug Mode
Switch on Debug Mode
Developer Mode""",
  "live_test_url"        :  "http://odoodemo.webkul.com/?module=web_debug",
  "depends"              :  ['web'],
  'assets': {
      'web.assets_backend': [
          'web_debug/static/src/js/web_debug.js',
          'web_debug/static/src/xml/web_debug.xml',
      ],
  },
  "images"               :  ['static/description/Banner.png'],
  "application"          :  True,
  "installable"          :  True,
  "auto_install"         :  False,
  "currency"             :  "EUR",
  "pre_init_hook"        :  "pre_init_check",
}
