odoo.define('web_enterprise.SwipeItemMixin', function () {

const SNAP_THRESHOLD = 46; // Correspond to o_menu_toggle "width"
const ANIMATION_SWIPE_DURATION = 250;

const SwipeItemMixin = {
    events: {
        'touchstart .o_swipe_item': '_onTouchStart',
        'touchmove .o_swipe_item': '_onTouchMove',
        'touchend .o_swipe_item': '_onTouchEnd',
    },

    /**
     * Add the class into the target element to be able to swipe.
     *
     * @private
     */
    addClassesToTarget: function () {
        this.$(this.selectorTarget).addClass('o_swipe_item');
    },

    /**
     *
     * @param options
     * {
     *    allowSwipe: handler call when item is moving, it's return true if the swipe event is allow
     *    onLeftSwipe: callback when swipe Right to Left
     *    onLeftSwipe: callback when swipe Left to Right
     *    selectorTarget: a query selector to find the target where swipe must be applied
     * }
     */
    init(options) {
        this.leftAction = options.onLeftSwipe;
        this.rightAction = options.onRightSwipe;
        this.allowSwipe = options.allowSwipe;
        this.selectorTarget = options.selectorTarget;
    },

    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    /**
     * Add the node actions elements to the DOM
     *
     * @private
     * @param {JQuery} $target
     */
    _addSwipeNode($target) {
        $('<div class="o_swipe_separator"/></div>').prependTo($target);
        if (this.rightAction) {
            $('<div class="o_swipe_action right" data-key="read"><i class="fa fa-check-circle fa-2x text-white"/></div>').prependTo($target);
        }
        if (this.leftAction) {
            $('<div class="o_swipe_action left" data-key="star"><i class="fa fa-star fa-2x text-white"/></div>').prependTo($target);
        }
    },

    /**
     * Called when item moving with touch
     * 
     * @private
     * @param {TouchEvent} ev
     * @param {false | 'left' | 'right'} action
     * @param {Number} xDelta
     * @return {Boolean} true if action allowed
     */
    _allowAction(ev, action, xDelta) {
        return this.allowSwipe ? this.allowSwipe(ev, action, xDelta) : true;
    },

    /**
     * Get the direction of the swipe
     * 
     * @param {{xDelta: Number, yDelta: Number}} touchDelta
     * @returns {false | 'left' | 'right'}
     */
    _getSwipeDirection(touchDelta) {
        return touchDelta.xDelta > 0 ? 'right' : touchDelta.xDelta < 0 ? 'left' : false;
    },

    /**
     * Get the delta between two touch
     * 
     * @private
     * @param {{x: Number, y: Number}} touch 
     * @param {{startLeft: Number, touchStart: {x: Number, y: Number}}} data 
     * @returns {{xDelta: Number, yDelta: Number}} 
     */
    _getTouchDelta(touch, data) {
        return {
            xDelta: touch.x - data.touchStart.x + data.startLeft,
            yDelta: touch.y - data.touchStart.y
        };
    },

    /**
     * Return postion an object with x, y of the touch event
     * 
     * @private
     * @param {TouchEvent} event 
     * @returns {{x: Number, y: Number}}
     */
    _getTouchPosition(event) {
        const changedTouch = event.changedTouches[0];
        return {
            x: changedTouch.clientX,
            y: changedTouch.clientY
        };
    },

    /**
     * Check if the threshold is reach
     * 
     * @private
     * @param {{xDelta: Number, yDelta: Number}} touchDelta 
     * @param {false | 'left' | 'right'} swipeDirection
     * @returns {false | 'left' | 'right'}
     */
    _isThresholdReach(touchDelta, swipeDirection) {
        if (Math.abs(touchDelta.xDelta) < SNAP_THRESHOLD) {
            return false;
        }
        return swipeDirection;
    },

    /**
     * Apply a left css property to the node
     * 
     * @private
     * @param {JQuery} $node
     * @param {String} left
     * @param {Boolean} animate
     */
    _moveLeft($node, left, animate) {
        if (animate) {
            $node.animate({
                left: left
            }, ANIMATION_SWIPE_DURATION);
        } else {
            $node.css('left', left);
        }
    },

    /**
     * Called when item moving with touch
     * 
     * @private
     * @param {TouchEvent} ev
     * @param {false | 'left' | 'right'} action
     * @param {Number} xDelta
     */
    _onElementMoving(ev, action, xDelta) {
        // we add here the background to swipe item
        if(action === 'right') {
            $(ev.currentTarget).children('.o_swipe_action.right').addClass('bg-success');
        } else if(action === 'left') {
            $(ev.currentTarget).children('.o_swipe_action.left').addClass('bg-warning');
        } else {
            $(ev.currentTarget)
            .children('.o_swipe_action')
            .removeClass([
                'bg-success',
                'bg-warning',
            ])
        }
    },

    /**
     * When the user end the swipe action
     *
     * @private
     * @param {TouchEvent} ev
     * @param {false | Function} callback
     */
    _performSwipeEndAction(ev, callback) {
        if (callback) {
            callback(ev);
        }
    },

    /**
     * Update the view to show the swipe at the correct position
     * 
     * @private
     * @param {JQuery} $target
     * @param {false | 'left' | 'right'} swipeDirection 
     * @param {Number} left 
     */
    _updateSwipePosition($target, swipeDirection, left) {
        this._moveLeft($target, left + 'px');
        if (swipeDirection) {
            this._moveLeft($target.find('.o_swipe_action.' + swipeDirection), -left + 'px');
        }
    },

    //--------------------------------------------------------------------------
    // Handlers
    //--------------------------------------------------------------------------

    /**
     * 
     * @private
     * @param {TouchEvent} ev 
     */
    _onTouchStart(ev) {
        const $target = $(ev.currentTarget);

        // apply a style to add radius on current target (like gmail)
        $target.addClass('o_swipe_current');
        $target.parent().addClass('overflow-hidden');
        this._addSwipeNode($target);
        $target.data('swipe_item', {
            touchStart: this._getTouchPosition(ev),
            startLeft: $target.css('left') === 'auto' ? 0 : parseInt($target.css('left'), 10),
            swipeDirection: false,
        });
    },

    /**
     * 
     * @private
     * @param {TouchEvent} ev 
     */
    _onTouchMove(ev) {
        const $target = $(ev.currentTarget);

        const data = $target.data('swipe_item');
        const touch = this._getTouchPosition(ev);
        const touchDelta = this._getTouchDelta(touch, data);
        const swipeDirection = this._getSwipeDirection(touchDelta);

        // Check for action to allow based on action and delta
        if(this.allowSwipe && !this._allowAction(ev, swipeDirection, touchDelta.xDelta)) {
            // update the swipe position to 0
            if (!data.swipeDirection || data.swipeDirection !== swipeDirection) {
                this._updateSwipePosition($target, swipeDirection, 0);
            }
            return;
        } else {
            data.swipeDirection = swipeDirection;
            $target.data('swipe_item', data);
        }

        // update animation
        this._updateSwipePosition($target, swipeDirection, touchDelta.xDelta);

        const swipeDirectionThresholdReach = this._isThresholdReach(touchDelta, swipeDirection);
        // trigger element moving
        this._onElementMoving(ev, swipeDirectionThresholdReach, touchDelta.xDelta);
    },

    /**
     * 
     * @private
     * @param {TouchEvent} ev 
     */
    _onTouchEnd(ev) {
        const $target = $(ev.currentTarget);

        // remove the radius on current target (like gmail)
        $target.removeClass('o_swipe_current');
        $target.parent().removeClass('overflow-hidden');

        const data = $target.data('swipe_item');
        const touch = this._getTouchPosition(ev);
        const touchDelta = this._getTouchDelta(touch, data);
        const swipeDirection = this._getSwipeDirection(touchDelta);

        this._moveLeft($(ev.currentTarget).find('.o_swipe_action'), 0, true);
        this._moveLeft($(ev.currentTarget), 0, true);
        $(ev.currentTarget).find('.o_swipe_action, .o_swipe_separator').remove();

        if(this.allowSwipe && !this._allowAction(ev, swipeDirection, touchDelta.xDelta)) {
            return;
        }

        // reset the direction
        data.swipeDirection = false;
        $target.data('swipe_item', data);

        const swipeDirectionWithThresholdReach = this._isThresholdReach(touchDelta, swipeDirection);

        let action = false;
        if (swipeDirectionWithThresholdReach === 'right' && this.rightAction) {
            action = this.rightAction;
        } else if (swipeDirectionWithThresholdReach === 'left' && this.leftAction) {
            action = this.leftAction;
        }
        this._performSwipeEndAction(ev, action);
    },
};

return SwipeItemMixin;
});
