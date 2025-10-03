# Fabricat (aka the "Management" Game)

🌐 [English](README.md) | [Русский](README.RU.md)

## Technical Specification

### Game Description

A networked economic strategy game for 2–4 players. Each controls a "company": buys raw materials (RMs), produces goods at factories, sells them (FGs) to the Exchange, takes and services loans, and pays expenses. The game proceeds in monthly rounds. The server acts as the Exchange and the sole rules arbiter.

#### Core Rules

* **Goal**: By the end of the game, avoid bankruptcy and have the highest capital.
* **Structure of a month (round)** — strict phase order:

  1. Deduct **fixed expenses** (warehouses, factories).
  2. The Exchange announces the **market of the month** (volumes and price corridors for RMs/FGs).
  3. **Buying RMs**: players submit hidden bids (quantity, price) → simultaneous reveal → allocation by descending price; in case of ties, **senior** player has priority.
  4. **Production**: player pays the launch cost and converts RMs into FGs according to factory capacities (basic/automated).
  5. **Selling FGs**: bids with prices ≤ monthly ceiling → Exchange buys in ascending price order; tie-break → senior.
  6. **Loans**: interest accrual, scheduled repayments, option to take new ones.
  7. **Construction/automation** of factories: submit orders and payments.
  8. Check **bankruptcies** and proceed to next month.
* **Senior player** always wins tie-breaks (equal prices/quantities/priority).
* **Game end**: when the set number of rounds is reached or only one non-bankrupt player remains.
* **Capital calculation**:

  * Cash + valuation of assets:

    * Factories at new construction cost
    * RMs at current minimum price
    * FGs at current maximum price
    * Outstanding loans
    * Unpaid residual construction payments

##### Default economic parameters (from the rules; configurable in session settings)

| Parameter                                | Default Value                                                                   |
| ---------------------------------------- | ------------------------------------------------------------------------------- |
| Starting capital                         | **\$10,000**                                                                    |
| Starting resources                       | **2 RMs**, **2 FGs**                                                            |
| Starting factories                       | **2 basic**                                                                     |
| Basic factory — launch                   | processes **1 RM**; launch cost **\$2,000**                                     |
| Automated factory — launch               | processes **up to 2 RMs**; launch cost **\$3,000**                              |
| Monthly warehouse expenses               | **\$300** per RM, **\$500** per FG in storage                                   |
| Monthly factory expenses                 | basic **\$1,000**, automated **\$1,500**                                        |
| Basic factory construction               | **\$5,000**, duration **5 mo.**, payments 50% upfront + 50% 1 mo. before launch |
| Automated factory construction           | **\$10,000**, duration **7 mo.**, payments 50% + 50%                            |
| Upgrade basic → automated                | **\$7,000**, duration **9 mo.**, operates as basic during upgrade               |
| Factory limit (incl. under construction) | **≤ 6**                                                                         |
| Loans                                    | **\$5,000** and **\$10,000**                                                    |
| Loan interest                            | **1%/mo.**; early repayment — **forbidden**                                     |
| Collateral/limits                        | loans secured by factories; total debt ≤ **½ guaranteed capital** (per rules)   |

###### Lobby configuration parameters (defaults shown)

1. Player starting capital — **\$10,000**
2. Starting resources: RMs — **2**
3. Starting resources: FGs — **2**
4. Starting factories: basic — **2**
5. Starting factories: automated — **2**
6. Basic factory: launch throughput (RMs per launch) — **1**
7. Basic factory: launch cost — **\$2,000**
8. Automated factory: launch throughput (max RMs per launch) — **2**
9. Automated factory: launch cost — **\$3,000**
10. Storage: monthly fee per RM — **\$300**
11. Storage: monthly fee per FG — **\$500**
12. Monthly expenses: basic factory — **\$1,000**
13. Monthly expenses: automated factory — **\$1,500**
14. Basic factory construction: total cost — **\$5,000**
15. Basic factory construction: duration (months) — **5**
16. Basic factory construction: payment share per instalment — **50%**
17. Basic factory construction: timing of final payment (months before delivery) — **1**
18. Automated factory construction: total cost — **\$10,000**
19. Automated factory construction: duration (months) — **7**
20. Automated factory construction: payment share per instalment — **50%**
21. Automated factory construction: timing of final payment (months before delivery) — **1**
22. Upgrade (basic → automated): cost — **\$7,000**
23. Upgrade (basic → automated): duration (months) — **9**
24. Upgrade: behavior during works (operates as basic) — **enabled**
25. Factory limit (including builds in progress) — **6**
26. Available loan #1 — **\$5,000**
27. Available loan #2 — **\$10,000**
28. Loan interest rate (per month) — **1%**
29. Early loan repayment — **disabled**
30. Debt limit: share of guaranteed capital — **0.5×**

##### Cumulative Seniority Rule

1. **Seniority order** is set for **each month** as an ordered list of players (position 1 — most senior).
2. **Initialization (month 1)**: each player rolls **1d6**. Lower roll = more senior. If ties occur, **only tied players reroll**, others are fixed.

   * Roll 1: P1 = 1; P2 = 3; P3 = 3
   * Roll 2: P2 = 1; P3 = 2
   * Final seniority: P1 > P2 > P3
3. **Order evolution**: at the start of each new month, the order **rotates cyclically** by 1 position relative to the previous month.
4. **Tie-break resolution**: the player with **higher seniority in the table** (i.e., with the **lower number**) wins.
5. **Example (3 players)**: cell value = seniority rank (1 = most senior).

| Month | Player 1 | Player 2 | Player 3 |
| ----- | -------: | -------: | -------: |
| 1     |        1 |        2 |        3 |
| 2     |        3 |        1 |        2 |
| 3     |        2 |        3 |        1 |
| 4     |        1 |        2 |        3 |

In month 3, a tie between Player 1 and Player 2 is resolved in favor of Player 1.

---

#### Core Restrictions

* **Players per session**: min **2**, max **4**.
* **Lobby wait time**: **60 seconds**. If ≥2 players within time → start; if 4 instantly → start without waiting; if <2 → session does not launch.
* **Lobby access**: join via unique 7-character key; key auto-generated when lobby is created.
* **Turn/decision time** per client (bid/action per phase): **60 seconds**. On timeout → treated as "skip"/"null bid".
* **No money transfers** between players — the only counterparty for money/trades is the **Exchange**.
* **Price corridors** and **market volumes** are set by the Exchange by current market level (levels 1–5; transitions by probability matrix).
* **Seniority role** — single per round; used for all tie-breaks via cumulative seniority rule.
* **Bankruptcy** — immediate elimination if unable to pay mandatory expenses/interest/installments.

---

### System Functions

#### Capabilities

**A. Sessions, users, access**

* User registration: **nickname** and **avatar** (≥10 catalog).
* Lobby entry: create room (invite code generation) or join via code.
* Enforce constraints: 2–4 players, 60s timer, auto-start/auto-close.

**B. Exchange role (server logic)**

* **Market generation** each month: RM supply, FG demand, price bounds. Supports market levels (1–5) and deterministic RNG (session seed).
* **Sealed bids**: receive client bids, simultaneous reveal, allocate:

  * for RMs — descending price until supply exhausted;
  * for FGs — ascending price until demand exhausted;
  * tie-breaks — **cumulative seniority rule**.
* **Production**: check available RMs and capacity, deduct costs, release FGs.
* **Loans**: issue (\$5k/\$10k), apply 1%/mo. interest, track repayment schedules, forbid early repayment, enforce collateral/limits.
* **Construction/upgrades**: queue management, timing and two-step payments, ≤6 factory limit (incl. under construction).
* **Expenses and storage**: monthly deductions for RMs/FGs held and factory upkeep.
* **Bankruptcies/victory**: auto-detect bankrupt players, stop game at last survivor, final capital calculation.
* **Reports**:

  * Monthly log (trades, production, expenses, interest, repayments, construction).
  * Player financial summary (cash, capital, assets, debt).
  * Bid reveal protocol (who, how much, at what price, what was bought/sold).
  * Per-player performance stats auto-aggregated over the last 10 games (average/best capital, wins, losses, win rate, longest and average match length in turns); viewable for the owner and other players.

**C. Seniority and tie-breaks (server)**

* **Initialization of month 1 order**: server rolls **1d6** for each player (visible in UI). Sort ascending. If ties → **only tied players reroll**.
* **Tie-break algorithm**: based on the seniority table, which rotates cyclically each turn.
* **Logging**: the tie-break "trace" (which month resolved the tie) is recorded in the journal.

**D. Client-side (UI/UX)**

* Lobby screen: connected players list, timer, avatar/nick selection, code entry/creation, basic session settings, **1d6 roll animation** at start.
* Game screen split into 4 quadrants (per player): avatar, nick, **capital**, **cash**, **debts**, **RMs/FGs** in storage, **factories** (statuses: active / idle / building / auto), active **loans**, **seniority indicator** (1…N).
* Phase action panel (bids editable until "Submit" or timeout):

  * "Buy RMs"
  * "Production"
  * "Sell FGs"
  * "Loan"
  * "Build/Automate"
  * "Skip"
* Month result screen and capital leaderboard; modal window for tie-break analysis (showing monthly seniority orders and the month that resolved the tie).

#### Restrictions

* **Architecture**: all economy and trades — on server (authoritative logic). Clients are not sources of truth.
* **Secrecy**: until reveal, players cannot see others' bid prices/quantities.
* **Consistency**: transactional phase application; one phase = one atomic calculation.
* **Determinism**: optional — RNG with seed (session level) for reproducibility; in this mode, 1d6 rolls are server-generated pseudorandom and reproducible.
* **Security**: forbid direct money transfers between players; validate bid prices/quantities against corridors/limits.
* **Logs**: action/system decision log stored immutably until session end.

---

### Player Functions

#### Capabilities

**Registration and entry**

* Set **nickname** and choose **avatar**; join session via code.
* Create session and configure start parameters (if "creator" rights).

**Round actions (by phase)**

* **Buy RMs**: submit bid (quantity, price) within month’s price corridor.
* **Production**: launch RM→FG conversion with launch cost; select volume ≤ capacity and available RMs.
* **Sell FGs**: submit bid (quantity, price) ≤ monthly ceiling.
* **Loans**: take new (\$5k/\$10k) if collateral/limit allow; view schedule and interest.
* **Construction/upgrade**: start new build or upgrade; pay 50% now and 50% one month before completion; track deadlines.
* **Skip**: explicitly skip phase/action (or timeout).
* **Analytics**: view the monthly log, last-10-game performance metrics (average/best capital, wins/losses, win rate, longest and average match length in turns) for yourself and other players, and the capital summary table.

#### Restrictions

* **Lobby limits**: 2–4 players; <2 → game won’t start.
* **Time**: any action/bid — **≤ 60s**; timeout = skip.
* **Finances**:

  * Cannot go negative in cash when paying for production/construction/expenses.
  * Loans only in **\$5k/\$10k** denominations; total debt ≤ ½ guaranteed capital; **early repayment forbidden**.
  * No money transfers to other players.
* **Trading**:

  * Bid prices must be within monthly corridors.
  * Bid allocation not guaranteed; in ties — **cumulative seniority rule**.
  * Remaining RMs/FGs after trades stay in storage and increase expenses.
* **Production/factories**:

  * Production limited by available RMs and factory capacity (1 RM per basic, up to 2 per automated).
  * Max factories (incl. under construction) **≤ 6**.
  * During upgrade, basic factory operates as basic for 9 months; costs/timings fixed.
* **Bankruptcy**: if unable to pay mandatory payments, player is eliminated immediately; all bids canceled.

---

## Appendices

### Phase action table (cheat sheet)

| Phase           | System action                               | Player action           |
| --------------- | ------------------------------------------- | ----------------------- |
| 1. Expenses     | Deducts warehouse and factory expenses      | —                       |
| 2. Market       | Publishes RM/FG volumes and price corridors | Analyze market          |
| 3. Buy RMs      | Collects & reveals bids; allocates          | Submit bid (qty, price) |
| 4. Production   | Validates, deducts costs, produces FGs      | Launch production       |
| 5. Sell FGs     | Collects & reveals bids; buys               | Submit bid (qty, price) |
| 6. Loans        | Accrues interest, collects payments         | Repay / take new        |
| 7. Construction | Manages timelines, enforces limits          | Submit build/upgrade    |
| 8. End of month | Checks bankruptcies, rotates order          | Review reports          |
