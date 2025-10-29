# Domain Overview — Milestone 1

This document captures the initial modeling decisions required for Milestone 1 of the game logic plan. It outlines the core domain entities and how data flows through a single month of gameplay. The intent is to give future implementation work concrete targets without locking the project into premature abstractions.

## Core Domain Entities

### GameSession
- Represents the overarching match or lobby.
- Owns immutable configuration (economic parameters, number of players, victory conditions) and the list of participating companies.
- Provides access to the deterministic random number generator (RNG) seed and hands out month identifiers.
- Coordinates persistence snapshots and high-level events.

### Company
- Player-controlled business entity.
- Tracks cash balance, outstanding loans, owned factories, resource inventory, finished goods inventory, and seniority ranking.
- Serves as the root for decision submissions (bids, production plans, loan requests, construction orders).
- Enforces invariants such as non-negative inventory counts and debt limit compliance before decisions are accepted.

### InventoryLedger
- Value object attached to a company encapsulating resources and finished goods.
- Supports atomic adjustments (accrual, spend, transfer between resource types) with validation against capacity constraints.
- Exposes read-only summaries for reporting phases.

### FactoryPortfolio
- Aggregates all factories owned or under construction for a company.
- Distinguishes factories by stage (operational, under construction, upgrading, mothballed) and tracks monthly capacity.
- Produces derived statistics (available capacity, launch costs due) for production and expense phases.

### FactoryBlueprint
- Immutable specification shared by all factories of a type (e.g., input requirements, output rate, maintenance costs).
- Referenced by `FactoryPortfolio` entries to avoid duplicating configuration.

### LoanAccount
- Represents a single loan with principal, interest rate, amortization schedule, and penalties.
- Provides methods to accrue interest, generate payment obligations, and check default conditions.
- Aggregated under a company to compute total debt exposure.

### MarketState
- Global structure for the month describing resource and finished good corridors, total demand, and clearing rules.
- Carries resolved auction results (prices, allocated volumes) for player visibility.
- Interfaces with the RNG to derive stochastic components (e.g., demand shocks) deterministically.

### PhaseContext
- Ephemeral container constructed for each phase execution.
- Carries the subset of game state and decisions relevant to the phase, plus logging hooks and RNG handles.
- Ensures phases do not mutate unrelated portions of the state.

### EventLog
- Append-only record capturing notable actions (bids, loan issuance, bankruptcies) with timestamps and metadata.
- Supports querying by company and month for UI playback and analytics.

## Single-Month Data Flow

1. **Month Initialization**
   - Inputs: Previous month snapshot, new month identifier from `GameSession`, pending decisions submitted by companies.
   - Operations: Create baseline `PhaseContext`, roll seniority updates if pending, instantiate deterministic RNG stream for the month, reset transient metrics (e.g., production usage).
   - Outputs: Prepared `PhaseContext` and per-company working copies of state.

2. **Expense Phase**
   - Inputs: Company cash balances, recurring obligations (factory maintenance, salaries, loan payments due).
   - Operations: Deduct expenses, call `LoanAccount` to post scheduled payments, flag companies failing to meet obligations.
   - Outputs: Updated cash balances, bankruptcies queued for resolution, entries in `EventLog`.

3. **Market Announcement Phase**
   - Inputs: `MarketState` configuration, RNG seed, aggregate factory capacity data.
   - Operations: Generate demand and supply corridors, publish price ceilings/floors for resources and finished goods.
   - Outputs: Updated `MarketState` distributed to companies for decision reference.

4. **Raw Material Purchase Resolution**
   - Inputs: Player bids submitted during decision window, current cash balances, seniority order.
   - Operations: Validate bids against cash and storage constraints, sort bids by price and seniority, allocate quantities via hidden auction mechanics, debit cash and update inventories.
   - Outputs: Adjusted cash and `InventoryLedger`, record of fulfilled and unfulfilled bids.

5. **Production Phase**
   - Inputs: Production orders per company, available raw materials, `FactoryPortfolio` capacity, launch cost obligations.
   - Operations: Consume raw materials, apply launch costs, schedule factory usage, create finished goods units, and note any underutilization.
   - Outputs: Updated inventories, cash adjustments, production reports for logging.

6. **Finished Goods Sale Resolution**
   - Inputs: Sale offers from companies, market demand corridor, seniority order, price ceilings.
   - Operations: Validate offers, prioritize by price then seniority, allocate demand, credit cash for sold goods, return unsold goods to inventory (or mark for storage costs).
   - Outputs: Updated cash balances, inventory changes, market clearing report.

7. **Loan Management Phase**
   - Inputs: Loan requests, current debt levels, configuration for credit limits.
   - Operations: Evaluate requests, issue approved loans (creating `LoanAccount` instances), compute interest accrual for existing loans, mark defaults for past-due accounts.
   - Outputs: Updated loan portfolios, cash disbursements, default notices.

8. **Construction & Upgrade Phase**
   - Inputs: Construction orders, `FactoryPortfolio` backlog, cash balances.
   - Operations: Validate affordability, deduct upfront costs, advance construction timers, move completed factories into operational status, apply upgrade effects.
   - Outputs: Updated factory states and cash adjustments, log of completed projects.

9. **End-of-Month Wrap-Up**
   - Inputs: All per-company states post phases, bankruptcy flags, seniority rotation rules.
   - Operations: Resolve bankruptcies (remove companies or trigger liquidation), rotate seniority where appropriate, finalize profit/loss summaries, persist snapshot via `GameSession`.
   - Outputs: Next month starting snapshot, finalized `EventLog` entries, metrics for analytics.

10. **Persistence & Notification**
    - Inputs: Finalized month state and logs.
    - Operations: Serialize state for storage adapters, emit notifications to interested systems (API gateways, observers).
    - Outputs: Durable record ready for the next month or API consumption.

These definitions and flow steps provide the foundational blueprint for implementing the subsequent milestones.
