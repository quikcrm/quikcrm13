odoo.define('mail_enterprise.widget.Thread', function (require) {

const config = require('web.config');
if (!config.device.isMobile) {
    return;
}
const core = require('web.core');
const ThreadWidget = require('mail.widget.Thread');
const SwipeItemMixin = require('web_enterprise.SwipeItemMixin');
const SnackBar = require('web_enterprise.SnackBar');

const _t = core._t;

ThreadWidget.include(Object.assign({}, SwipeItemMixin, {
    events: Object.assign({}, SwipeItemMixin.events, ThreadWidget.prototype.events),
    init() {
        SwipeItemMixin.init.call(this, {
            allowSwipe: (ev, action) => {
                return action === 'left' && this._allowLeftSwipe(ev);
            },
            onLeftSwipe: ev => {
                this._toggleStarDisplay(ev);
                let params = {
                    message: _t('Toggle star'),
                    delay: 3000,
                    onComplete: () => this.trigger('toggle_star_status', this._retrieveMessageId(ev)),
                    actionText: _t('UNDO'),
                    onActionClick: () => {
                        this._toggleStarDisplay(ev);
                    },
                };
                // the message is only remove on mailbox starred thread
                if ('mailbox_starred' === this._currentThreadID) {
                    const $target = $(ev.currentTarget);
                    params.message = _t('Unstar message');
                    params.onActionClick = () => {
                        this._toggleStarDisplay(ev);
                        $target.slideDown('fast');
                    };
                    $target.slideUp('fast', () => new SnackBar(this, params).show());
                } else {
                    new SnackBar(this, params).show();
                }
            },
            selectorTarget: '.o_thread_message',
        });
        return this._super(...arguments);
    },
    render(thread, options) {
        options = Object.assign({}, options, {
            displayMarkAsRead: false,
        });
        let renderResult = this._super(thread, options);
        SwipeItemMixin.addClassesToTarget.call(this);
        return renderResult;
    },
    _allowLeftSwipe(ev) {
        return this._getThreadMessageStar(ev).length > 0;
    },
    _getThreadMessageStar(ev) {
        return $(ev.currentTarget).find('.o_thread_message_star');
    },
    _retrieveMessageId(ev) {
        return $(ev.currentTarget).data('message-id');
    },
    _toggleStarDisplay(ev) {
        this._getThreadMessageStar(ev)
            .toggleClass('fa-star-o')
            .toggleClass('fa-star');
    },
}));

});
