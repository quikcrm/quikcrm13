# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import itertools
from . import common


def record_powerset(records):
    def flatten_subset(subset):
        if len(list(subset)):
            recordset = subset[0]
            for record in subset[1:]:
                recordset += record
        else:
            recordset = records.browse()
        return recordset

    powerset = list()
    for n in range(len(records) + 1):
        for subset in itertools.combinations(records, n):
            powerset.append(flatten_subset(subset))
    return powerset


class TestSaleCouponPriceTaxCloud(common.TestSaleCouponTaxCloudCommon):

    def test_total(self):
        """Test that the sum of TaxCloud is equal to the order total
           (with applied discounts), for all possible sets of discounts.
           This is the most important coherency issue.
           So we don't test how coupon are applied, just that the result of our
           computations match what is obtained from the lines.
        """
        TaxCloud = self.order._get_TaxCloudRequest("id", "api_key")

        for applied_discounts in record_powerset(self.all_programs):
            self.order.applied_coupon_ids = applied_discounts.mapped('coupon_ids')
            self.order.recompute_coupon_lines()
            lines = self.order.order_line
            TaxCloud._apply_discount_on_lines(lines)
            sum_taxcloud = sum(lines.filtered(lambda l: l.price_taxcloud > 0)
                               .mapped(lambda l: l.price_taxcloud * l.product_uom_qty))

            self.assertEqual(sum_taxcloud, self.order.amount_total)

    def test_free_product(self):
        """This one is kind of a corner case.
           While the free product program seems well-configured, due to the way
           it computes the quantity it does not offer 1 free C but (12/2=)6!
           Don't ask me why, I did not code this. Anyway.
           Given that this makes a product-specific discount of 60$ over a line
           of 10$, our algorithm is supposed to first max the product C line and
           then evenly apply the remaining 50$ over the other lines.
        """
        TaxCloud = self.order._get_TaxCloudRequest("id", "api_key")

        Apply = self.env['sale.coupon.apply.code']
        Apply.apply_coupon(self.order, self.program_free_product_C.coupon_ids.code)

        discount_line = self.order.order_line.filtered('coupon_program_id')
        self.assertEqual(discount_line.price_unit, -10)
        self.assertEqual(discount_line.product_uom_qty, 6)

        lines = self.order.order_line
        TaxCloud._apply_discount_on_lines(lines)

        line_C = lines.filtered(lambda l: l.product_id == self.product_C)
        self.assertEqual(line_C.price_taxcloud, 0)

        other_lines = lines.filtered(lambda l: l.price_taxcloud > 0) - line_C
        sd = sum(other_lines.mapped(lambda l: l.price_taxcloud * l.product_uom_qty))
        s = sum(other_lines.mapped(lambda l: l.price_unit * l.product_uom_qty))

        self.assertEqual(sd, s - 50, "The remainder was applied on other lines.")
        ratio = sd / s
        # moreover, the remainder was applied evenly on other lines:
        for line in other_lines:
            self.assertAlmostEqual(line.price_taxcloud, line.price_unit * ratio)
