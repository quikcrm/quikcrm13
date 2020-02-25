odoo.define('stock_enterprise.ReportGridController', function (require) {
"use strict";

var GridController = require('web_grid.GridController');
var utils = require('web.utils');

var ReportGridController = GridController.extend({
    /**
     * @override
     * @return {Promise} Override magnifying glass click function in order to
     * excute an action that display the stock.move for the selected grid
     * cell.
     *
     */
    _onClickCellInformation: function (e) {
        var self = this;
        var $target = $(e.target);
        var state = this.model.get();
        var cellPath = $target.parent().attr('data-path').split('.');
        var rowPath = cellPath.slice(0, -3).concat(['rows'], cellPath.slice(-2, -1));
        var row = utils.into(state, rowPath);
        var colPath = cellPath.slice(0, -3).concat(['cols'], cellPath.slice(-1));
        var col = utils.into(state, colPath);
        return this._rpc({
            model: 'report.stock.quantity',
            method: 'action_open_moves',
            args: [
                row.values.product_id[0],
                row.values.state,
                col.values.date[0].split('/')[0],
            ]
        }).then(function (action) {
            return self.do_action(action);
        });
    },
});

return ReportGridController;

});
