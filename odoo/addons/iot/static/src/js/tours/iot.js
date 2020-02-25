odoo.define('iot.tour', function (require) {
'use strict';

var core = require('web.core');
var tour = require('web_tour.tour');

var _t = core._t;

tour.register('iot_token_tour', {
    url: "/web",
}, [tour.STEPS.SHOW_APPS_MENU_ITEM, {
    trigger: '.o_app[data-menu-xmlid="iot.iot_menu_root"]',
    content: _t('Click on iot App.'),
    position: 'right'
}, {
    trigger: '.btn-primary',
    content: _t('Open wizard to scan range.'),
    position: 'right'
}, {
    trigger: '.o_clipboard_button',
    content: _t('Copy token to the clipboard.'),
    position: 'right'
}, {
    trigger: '.add_scan_range',
    content: _t('Add range to scan.'),
    position: 'right',
    run: function (actions) {
        $("input[name='add_scan_range_ip']").val('Text');
        actions.auto(".add_scan_range");
    },
}, {
    trigger: '.is-invalid',
    content: _t('The range can not be empty.'),
    position: 'right'
}, {
    trigger: '.add_scan_range',
    content: _t('Add range to scan.'),
    position: 'right',
    run: function (actions) {
        $("input[name='add_scan_range_ip']").val('10.30.10.');
        actions.auto(".add_scan_range");
    },
}]);

});


