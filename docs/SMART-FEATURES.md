# Smart dining and merchant analytics — upgraded design

Implemented and locally verified on 2026-11-27. This extends the existing 16-table SQLite application without changing its persisted schema or resetting existing data. No external model, AI service, or real payment is required.

## 1. Explainable personalized recommendations

The original `recommended` ordering used store IDs. `backend/insights.py` now derives a preference profile using three sources: a saved favorite (weight 3), a review of at least 4 stars (weight 2), and a previous purchase (weight 2, counted once per store). A store's category and district inherit those weights. Category interest `I` and district affinity `D` are each their matching weight divided by the total evidence weight. Each lies in [0,1]. All private signals are filtered by the current session user.

For reputation `R`, use the existing rounded average rating `a` and review count `n`: `(n*a + 5*3.5)/(n+5)/5`. The five-review prior of 3.5 stars reduces the advantage of a new store with just one perfect review. The discount feature `V` is the maximum `(1-current/original)` for active, in-stock, unexpired coupons at the store, or zero if there is no eligible coupon. Original prices of zero produce no discount ratio.

With evidence, score `100*(0.35*I + 0.25*R + 0.20*D + 0.20*V)`. Without evidence (new customer or guest), use `100*(0.65*R + 0.35*V)`. These are explicit heuristic weights, not a trained model or a calibrated probability. The two contexts should not be compared as if they were one universal satisfaction scale. Store IDs break ties after rounded scores. Only active stores matching the user's search and filters enter the ranking. The full result count and paginated ranking come from a read snapshot.

The SQL uses `UNION ALL`, `GROUP BY`, CTEs, joins and scalar aggregates. UI cards explain the category, reputation, region and discount components. Baseline behavior, cold start, a favorite added, a favorite removed, result order, and filter/pagination consistency were checked using temporary databases.

## 2. Group dining decision support

One organizer enters 2–8 members' integer HK-dollar budgets and preferred dining categories; all can agree on an optional common district. Participants are generic numbered rows, not individual user accounts. The form uses an ephemeral `VALUES` relation and only reads data; no private preferences are persisted. An unrestricted category is accepted by every category. Estimated per-person price must be within each member's budget (equivalently, no higher than the minimum budget); the selected shared district is also a hard constraint. Empty results are reported honestly without relaxing constraints automatically.

For every candidate store and member, calculate

`satisfaction = 100*(0.65*category_match + 0.25*R + 0.10*(1-price/budget))`.

The category match is binary. `R` is the same smoothed reputation used above. The eligible budget condition keeps the remaining-budget term nonnegative. `CROSS JOIN` creates candidate/member pairs; `MIN`, `AVG` and `SUM` aggregate worst-member satisfaction, average satisfaction, and category acceptance count. Sort by the unrounded minimum descending, then unrounded mean, then stable store ID. Display scores rounded to one decimal. Ranking by minimum first avoids sacrificing a member solely to increase the group's average; it does not guarantee that conflicting categories can all be satisfied.

Demonstration: budgets HK$100, HK$150, HK$120, with coffee, Asian food and unrestricted categories. On the original six-store demo, the two eligible stores are Daily Grind Causeway Bay and Tsim Sha Tsui; the expanded rich demo includes additional eligible branches. Set every budget above HK$180 to enlarge the candidate set; set one budget to HK$1 for an empty result. The values are fictional estimates and not actual bills. The formula encodes a design choice rather than a measured prediction of real diner preferences.

## 3. Merchant decision-support views

The analysis is scoped to an active `store_staff` membership and a selected authorized branch. The default period is the most recent seven Hong Kong calendar dates including today, switchable to 30. All metrics reflect simulated purchase snapshots, not actual revenue. Selling price and expiry are read from the immutable order, not the current coupon.

- Order cohort: orders purchased within the period; gross simulated sales, sold count, redeemed count, currently expired/unused counts, and redemption rate (`redeemed/sold`, null if zero). The redeemed state is current, not limited to redemption events occurring within the purchase period. Today uses separate Hong Kong date bounds.
- Daily sales: recursive calendar CTE fills zero-sale days; aggregate sale count and integer-cent gross by date; window `SUM(...) OVER (ORDER BY day)` provides cumulative sales.
- Offer ranking: preaggregate sales before joining current inventory; `DENSE_RANK` groups equal order counts, preserving unsold coupons. Active nonexpired offers at or below five available units carry a low-stock flag. Suggest `max(0, ceil(3*sold/days)-available_stock)` units to cover an illustrative next-three-day demand based on observed period average. No automatic restocking occurs, and this heuristic is not demand forecasting.
- Branch ranking: aggregate independently over the current user's active staff memberships, including branches with zero sales. Branch and coupon rankings return at most 50 rows. Selected-branch summaries cover all matching orders.
- Review statistics: current reviews grouped by their creation date (current ratings, count and mean); edited/deleted reviews do not preserve historical rating versions.

The API returns only aggregate analytics and branch/offer descriptions, not a buyer list or session credentials. In an isolated HTTP test, an actual simulated voucher purchase increments order/sales counts and decrements stock; redeeming it increases the redeemed count without changing gross sales. Unauthorized guest, ordinary customer and other branch requests are rejected. The real browser confirmed the seven-/30-day selector, selected branch changes, and the updated view.

## 4. Transaction contention evaluation

Run `python3 -B evaluation/transaction_benchmark.py`. It creates independent temporary databases, 100 fictional buyers per run, 10 initial vouchers, and 1, 8 or 32 worker threads. It calls the same SQLite purchase transaction used by the service over independent connections. Replays of successful purchases use the same request identity. All 15 measured runs sold exactly 10, rejected 90 as sold out, left zero stock, and had no busy result or duplicate order. Actual measurements and an explanation of the single-writer tradeoff are in the [transaction report](../evaluation/results/transactions-2026-11-27-125150/summary.md). These are local operation measurements including connection setup, not HTTP load capacity.

## 5. Performance and evidence

The [November rerun](../evaluation/results/insights-pagination-2026-11-27/summary.md) includes the new score/reason fields. In the 2,000-store/100,000-review/50,000-order condition, the combined guest bootstrap plus first 12 results was 13.24 KiB and 27.25 ms median versus 28.64 MiB and 339.94 ms for the preserved unpaginated baseline. The October simple-ordering result was 11.04 KiB and 2.79 ms; the richer recommendation ranks candidates before limiting and therefore has real computational cost. Comparing runs across dates is descriptive, not a controlled estimate of ranking overhead. Readability, correctness and response size remain bounded by pagination; time can still grow with candidate count and history.

Local verification: 18 database tests, 29 HTTP integration tests, one rich-demo generator test and two frontend behavior/adapter scripts passed. The browser demonstrated three-member matching with a budget cap, branch and time-period analytics switching, and signed-in personalized ranking. The group page had no horizontal overflow at 390 CSS pixels. Tests did not modify the existing demo DB. All new queries use the existing indexes and schema; no migration is required. [API](API.md), [demonstration](DEMO-GUIDE.md) and [evaluation](../evaluation/README.md) explain how to reproduce.

For recording, `python3 -B run.py --smart-demo` selects a separate database using `backend/smart_demo.py`. A deterministic seed adds 111 historical simulated purchases and 48 fictional reviews to the ordinary seed, reconciles coupon stock, uses valid purchase/redemption dates and validates integrity. It never replaces or adds data to an existing file; this dataset is not the concurrency dataset or a real-world evaluation.

Actual browser screenshots from an isolated fictional demo database: [personalized recommendations](images/personalized-recommendation.png), [group matching](images/group-match.png), [merchant analytics](images/merchant-analytics.png).

## 6. Limitations and potential next work

The recommendation model uses hand-selected weights, not learned preference prediction; no real interaction logs or user-study outcomes are claimed. Group preferences are entered by one local organizer, with no remote group invitation or live voting. The analytics summarize the current local dataset; no payment or production service has been deployed. A future project could compare group satisfaction policies through a real user study or benchmark candidate scoring across a wider workload before changing its indexes or architecture.
