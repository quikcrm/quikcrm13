odoo.define('mail.thread_window_mobile_tests', function (require) {
"use strict";

const mobile = require('web_mobile.rpc');
const mailTestUtils = require('mail.testUtils');
const {createParent, nextTick} = require('web.test_utils');

QUnit.module('mail', {}, function () {

QUnit.module('Discuss in mobile', {
    beforeEach() {
        this.services = mailTestUtils.getMailServices();
        this.data = {
            'mail.message': {
                fields: {},
            },
            'initMessaging': {
                channel_slots: {
                    channel_channel: [{
                        id: 1,
                    }],
                },
            },
        };
    },
});

QUnit.test('close thread window using backbutton event', async function (assert) {
    assert.expect(5);

    const __overrideBackButton = mobile.methods.overrideBackButton;
    mobile.methods.overrideBackButton = function () {};

    const parent = createParent({
        data: this.data,
        services: this.services,
        mockRPC(route, args) {
            if (args.method === 'channel_fold') {
                assert.ok(true, "should call channel_fold");
                return $.when();
            }
            return this._super.apply(this, arguments);
        },
    });
    await nextTick();

    // get channel instance to link to thread window
    const channel = parent.call('mail_service', 'getChannel', 1);
    await nextTick();
    assert.ok(channel, "there should exist a channel locally with ID 1");

    channel.detach();
    await nextTick();
    assert.containsOnce($('body'), '.o_thread_window',
        "there should be a thread window");
    assert.isVisible($('.o_thread_window'),
        "there should be an opened thread window");

    const backButtonEvent = new Event('backbutton');

    // simulate 'backbutton' event triggered by the app
    document.dispatchEvent(backButtonEvent);
    // waiting nextTick to match testUtils.dom.triggerEvents() behavior
    await nextTick();

    assert.containsNone($('body'), '.o_thread_window',
        "the thread window should be closed");

    parent.destroy();
    mobile.methods.overrideBackButton = __overrideBackButton;
});

});
});
