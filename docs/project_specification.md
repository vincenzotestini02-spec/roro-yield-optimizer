# PROJECT SPECIFICATION: DFDS Ro-Ro Deck Stowage & Dynamic Yield Optimizer

---

## 1. Executive Summary & Purpose

### 1.1 Context & Objective
This project is an operational and commercial decision-support system designed for short-sea Roll-on/Roll-off (Ro-Ro) and Ro-Pax ferry operations, modeled directly on the core business challenges of **DFDS Ferry Division**. 

The tool bridges the structural friction between two critical business departments:
1. **Ferry Operations:** Focused on safety, lane-metre packing, structural deadweight cargo limits, hazardous/reefer compatibility, and terminal turnaround time.
2. **Ferry Commercial:** Focused on revenue management, maximizing **RevPAL** (*Revenue Per Available Lane-Metre*), managing long-term contracted volume commitments (Key Accounts) versus volatile, high-margin Spot market demand.

### 1.2 Target Audience & Evaluation Standard
This specification is designed both as a high-impact portfolio artifact for the **DFDS Graduate Programme** and as a foundational system specification for another AI agent to ingest, critique, or expand into custom mathematical formulations derived from external academic papers.

---

## 2. Industry Problem Statement

### 2.1 The Operational Bottleneck (Operations)
In short-sea Ro-Ro operations, cargo space cannot be evaluated merely by total container slots (TEU) or aggregate tonnage. The defining operational unit is **Lane Metres** (the cumulative linear length of deck lanes dedicated to trailers, trucks, and trade cars):
* **Heterogeneous Units:** Cargo consists of varied physical profiles (13.6 m standard semi-trailers, 16.5 m accompanied driver rigs, 12.2 m heavy mafi roll-trailers, and variable-length automotive cargo).
* **Multi-Dimensional Constraints:** Packing a vessel involves physical length limits, maximum deadweight tonnage (DWT), reefer electrical plug saturation, axle-load constraints, and draft/trim stability requirements.
* **Broken Stowage & Lashing Buffers:** Real-world maritime packing cannot place trailers bumper-to-bumper. A physical safety gap ($\Delta_{\text{lashing}}$) must be maintained between units for crew lashing and terminal tractor clearance.

### 2.2 The Commercial Trade-Off (Commercial)
Ferry capacity is a perishable asset: once the vessel sails, any unutilized lane metre represents irreversibly lost marginal profit.
* **Contracted B2B (Key Accounts):** Large industrial forwarders book guaranteed allocations at lower negotiated freight rates ($\text{EUR}/\text{m}$). These provide baseline demand and hedge volume risk, but lock up capacity.
* **Spot Market Freight:** Small hauliers and ad-hoc shippers book with short lead times at premium spot rates, frequently supplemented by auxiliary charges (e.g., electrical plug connection fees for reefers).
* **Booking Allocation Dilemma:** Standard industry practice often relies on First-Come-First-Served (FCFS) rules. If low-yield contractual freight fills the deck early, higher-yield spot bookings must be rejected, suppressing total vessel contribution margin.

---

## 3. Core Conceptual Architecture

The system treats cargo acceptance and deck allocation as an integrated **Multi-Dimensional Knapsack & Yield Optimization Problem**.

```
[ Inbound Booking Stream ]
   │
   ├── Segment A: Contracted Key Accounts (Baseline Volumes)
   └── Segment B: High-Yield Dynamic Spot Requests
   │
   ▼
[ Mathematical Optimization Core (MILP) ]
   ├── Objective: Maximize Net Marginal Profit per Sailing (RevPAL)
   ├── Subject to Physical Bounds:
   │    ├── Cumulative Effective Lane-Metres ≤ Total Vessel Capacity
   │    ├── Cumulative Cargo Weight ≤ Max Permissible Deadweight (DWT)
   │    └── Active Reefer Units ≤ Total Available Vessel Plugs
   └── Subject to Commercial Policy:
        └── Enforce contractual quota floors for Key Account forwarders
   │
   ▼
[ Dual Operational & Commercial Outputs ]
   ├── Operations: Terminal Manifest & Stowage Feasibility Sheet
   └── Commercial: RevPAL Uplift, Rejection Justifications & Margin Delta
```

---

## 4. Mathematical & Algorithmic Formulation

### 4.1 Decision Variables
For a set of $N$ incoming booking requests, define a binary decision variable $x_i$:
$$x_i \in \{0, 1\} \quad \forall i \in \{1, 2, \dots, N\}$$
Where:
* $x_i = 1$ if booking request $i$ is accepted and loaded onto the vessel.
* $x_i = 0$ if booking request $i$ is rejected, waitlisted, or rolled over to a subsequent sailing.

### 4.2 Objective Function (Net Margin Maximization)
The primary objective is to maximize the aggregate voyage margin:
$$\max \sum_{i=1}^{N} \Big( \text{Revenue}_i - \text{VariableHandlingCost}_i \Big) \cdot x_i$$

Where:
* $\text{Revenue}_i = (\text{NominalLength}_i \cdot \text{RatePerMetre}_i) + \text{SurchargeReefer}_i$
* $\text{VariableHandlingCost}_i = \text{TerminalStevedoringCost} + f(\text{Weight}_i, \text{NominalLength}_i)$

### 4.3 Constraint Set

1. **Linear Deck Capacity (with Broken Stowage Allowance):**
   $$\sum_{i=1}^{N} \Big( \text{NominalLength}_i + \Delta_{\text{lashing}} \Big) \cdot x_i \le \text{TotalLaneMetres}$$
   *(Where $\Delta_{\text{lashing}}$ accounts for inter-trailer safety spacing and lashing access).*

2. **Deadweight Cargo Tonnage Limit:**
   $$\sum_{i=1}^{N} \text{Weight}_i \cdot x_i \le \text{MaxCargoDWT}$$

3. **Reefer Electrical Infrastructure Constraint:**
   $$\sum_{i=1}^{N} \text{IsReefer}_i \cdot x_i \le \text{AvailableReeferPlugs} \quad (\text{where } \text{IsReefer}_i \in \{0, 1\})$$

4. **Commercial Contractual Minimum Quota (Key Accounts Protection):**
   $$\sum_{i \in \text{KeyAccounts}} \text{NominalLength}_i \cdot x_i \ge \text{ContractedGuaranteedMetres}$$

---

## 5. Key Performance Indicators (KPIs)

The model measures performance across both domains:

| Metric | Business Definition | Operational / Commercial Meaning |
| :--- | :--- | :--- |
| **RevPAL** | $\frac{\text{Total Voyage Revenue}}{\text{Available Vessel Lane-Metres}}$ | The universal shipping efficiency metric: revenue generated per unit of available linear inventory. |
| **Deck Utilization Factor** | $\frac{\sum \text{Effective Length Stowed}}{\text{Available Lane-Metres}} \times 100$ | Measures operational waste and remaining linear buffer capacity. |
| **Deadweight Saturation** | $\frac{\sum \text{Weight Stowed}}{\text{Max Cargo DWT}} \times 100$ | Prevents vessel draft violations while evaluating cargo density balance. |
| **Yield Delta vs. FCFS** | $\frac{\text{Margin}_{\text{Optimal}} - \text{Margin}_{\text{FCFS}}}{\text{Margin}_{\text{FCFS}}} \times 100$ | Demonstrates the direct financial value of algorithmic optimization over standard booking acceptance. |

---

## 6. Functional Requirements for the Software Implementation

1. **Simulation Input Engine:**
   * Synthesize realistic Ro-Ro cargo demand profiles (standard dry trailers, reefer units, tractor units with drivers, heavy mafi platforms, and commercial vans).
   * Parameterize rate premiums, spot markups, and reefer electrical plug charges.
2. **Deterministic Optimization Engine:**
   * Formulate and solve the problem using Mixed-Integer Linear Programming (MILP).
   * Guarantee strict compliance with linear capacity, deadweight, and reefer plug boundaries.
3. **Comparative Baseline Benchmark:**
   * Run a parallel First-Come-First-Served (FCFS) heuristic algorithm on identical booking queues to prove optimization gains.
4. **Interactive Visualization Layer:**
   * Visual deck packing distribution (stowed vs. rejected units categorized by type).
   * Commercial yield distribution showing rate-per-metre acceptance curves across segments.
   * Exportable loading manifest for terminal stevedoring planning.

---

## 7. Instructions for Ingesting Agents / Downstream Models

When using this document as an input prompt or context for expanding the model:
* **Academic Grounding:** Incorporate specialized academic literature provided by the user regarding multi-deck weight distribution, stability calculation (trim/metacentric height $GM$), or advanced stochastic revenue management.
* **Preserve the Business Logic:** Maintain the tension between **Ferry Operations** (physical deck bottlenecks) and **Ferry Commercial** (contractual vs. spot revenue optimization).
* **Focus on Practical Application:** Ensure all suggested formulas or code enhancements are deliverable within a lightweight, verifiable environment (e.g., Python using standard scientific libraries such as `scipy`, `pulp`, `numpy`, and `streamlit`).