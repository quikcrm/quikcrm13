odoo.define('web_enterprise.mobile_menu_tests', function (require) {
"use strict";

var testUtils = require('web.test_utils');
var testUtilsEnterprise = require('web_enterprise.test_utils');

QUnit.module('web_enterprise mobile_menu_tests', {
    beforeEach: function () {
        this.data = {
            all_menu_ids: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            name: "root",
            children: [{
                id: 1,
                name: "Discuss",
                children: [],
             }, {
                 id: 2,
                 name: "Calendar",
                 children: []
             }, {
                id: 3,
                name: "Contacts",
                children: [{
                    id: 4,
                    name: "Contacts",
                    children: [],
                }, {
                    id: 5,
                    name: "Configuration",
                    children: [{
                        id: 6,
                        name: "Contact Tags",
                        children: [],
                    }, {
                        id: 7,
                        name: "Contact Titles",
                        children: [],
                    }, {
                        id: 8,
                        name: "Localization",
                        children: [{
                            id: 9,
                            name: "Countries",
                            children: [],
                        }, {
                            id: 10,
                            name: "Fed. States",
                            children: [],
                        }],
                    }],
                 }],
           }],
        };
    }
}, function () {

    QUnit.module('Burger Menu');

    QUnit.test('Burger Menu on home menu', async function (assert) {
        assert.expect(3);

        var mobileMenu = await testUtilsEnterprise.createMenu({ menuData: this.data });

        if (mobileMenu.$burgerMenu.length) {
            var menuInMobileMenu = mobileMenu.$burgerMenu[0].querySelector('.o_burger_menu_user');
            assert.ok(menuInMobileMenu !== null, 'node with class o_burger_menu_user must be in Burger menu');
            if (menuInMobileMenu) {
                var subMenuInMobileMenu = menuInMobileMenu.querySelector('.o_user_menu_mobile');
                assert.ok(subMenuInMobileMenu !== null, 'sub menu (.o_user_menu_mobile) must be in Burger menu');
            }
        }

        await testUtils.dom.click(mobileMenu.$('.o_mobile_menu_toggle'));
        assert.isVisible($(".o_burger_menu"),
            "Burger menu should be opened on button click");
        await testUtils.dom.click($('.o_burger_menu_close'));

        mobileMenu.destroy();
    });

    QUnit.test('Burger Menu on an App', async function (assert) {
        assert.expect(4);

        var mobileMenu = await testUtilsEnterprise.createMenu({ menuData: this.data });

        mobileMenu.change_menu_section(3);
        mobileMenu.toggle_mode(false);

        await testUtils.dom.click(mobileMenu.$('.o_mobile_menu_toggle'));
        assert.isVisible($(".o_burger_menu"),
            "Burger menu should be opened on button click");
        assert.strictEqual($('.o_burger_menu .o_burger_menu_app .o_menu_sections > *').length, 2,
            "Burger menu should contains top levels menu entries");
        await testUtils.dom.click($('.o_burger_menu_topbar'));
        assert.doesNotHaveClass($(".o_burger_menu_content"), 'o_burger_menu_dark',
            "Toggle to usermenu on header click");
        await testUtils.dom.click($('.o_burger_menu_topbar'));
        assert.hasClass($(".o_burger_menu_content"),'o_burger_menu_dark',
            "Toggle back to main sales menu on header click");

        mobileMenu.destroy();
    });
});
});
