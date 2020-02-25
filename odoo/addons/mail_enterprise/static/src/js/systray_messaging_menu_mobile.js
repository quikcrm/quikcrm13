odoo.define('mail_enterprise.systray.MessagingMenu', function (require) {

const config = require('web.config');
if (!config.device.isMobile) {
    return;
}
const core = require('web.core');
const MessagingMenu = require('mail.systray.MessagingMenu');
const SwipeItemMixin = require('web_enterprise.SwipeItemMixin');
const SnackBar = require('web_enterprise.SnackBar');

const _t = core._t;

MessagingMenu.include(Object.assign({}, SwipeItemMixin, {
    events: Object.assign({}, SwipeItemMixin.events, MessagingMenu.prototype.events),
    init() {
        SwipeItemMixin.init.call(this, {
            allowSwipe: (ev, action) => {
                return action === 'right' && this._allowRightSwipe(ev);
            },
            onRightSwipe: ev => {
                const $preview = this._getPreviewFromSwipe(ev);
                this._toggleUnReadPreviewDisplay(ev);
                const isNotificationNotDiscuss = isNaN($preview.data('preview-id'));
                let params = {
                    message: _t('Marked as read'),
                    delay: 3000,
                    onComplete: () => this._markAsRead($preview),
                    actionText: _t('UNDO'),
                    onActionClick: () => {
                        this._toggleUnReadPreviewDisplay(ev);
                    }
                };
                if (isNotificationNotDiscuss) {
                    const $target = $(ev.currentTarget);
                    params.onActionClick = () => {
                        this._toggleUnReadPreviewDisplay(ev);
                        $target.slideDown('fast');
                    };
                    $target.slideUp('fast', () => new SnackBar(this, params).show());
                } else {
                    new SnackBar(this, params).show();
                }
            },
            selectorTarget: '.o_mail_preview',
        });
        return this._super(...arguments);
    },
    _allowRightSwipe(ev) {
        const $preview = this._getPreviewFromSwipe(ev);
        const previewID = $preview.data('preview-id');
        if ('mailbox_inbox' === previewID || 'mail_failure' === previewID) {
            return true;
        } else {
            return $preview.data('unread-counter') > 0;
        }
    },
    _getPreviewFromSwipe(ev) {
        return $(ev.currentTarget);
    },
    _renderPreviews: function () {
        this._super(...arguments);
        SwipeItemMixin.addClassesToTarget.call(this);
    },
    _toggleUnReadPreviewDisplay(ev) {
        this._getPreviewFromSwipe(ev).toggleClass('o_preview_unread');
    },
}));
});
