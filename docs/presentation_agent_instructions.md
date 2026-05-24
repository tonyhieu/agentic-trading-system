# Instructions for Presentation Generation Agent

You are an expert technical content creator and presentation designer. Your task is to generate materials for a group presentation summarizing the latest algorithmic trading research experiments.

## 1. Experiment Context
The research team has been iterating on execution algorithms to improve the performance of a noisy "oracle" signal (win rate ~37%, noise sigma=5). The baseline algorithm (`simple`) indiscriminately executes every order, suffering heavy adverse selection and building up large compounding losses. The goal was to build "gating" and "sizing" algorithms that condition on market microstructure or portfolio state to skip or scale down trades during adverse regimes.

## 2. Packaged Results: Top 3 Algorithms

### A. Position Tier Gate (ptg-m-l1 / ptg-f-l7)
- **Mechanism:** Caps concurrent open exposure. It skips new open-leg executions if the portfolio's absolute net position is at or above a threshold (1 contract). It prevents runaway adverse selection on compounded positions when the oracle is consistently wrong.
- **Performance:** **+2632%** Realized PnL vs Baseline.
- **Key Insight:** Concentrates execution on "fresh" entries when the portfolio is flat, strictly limiting drawdown in adverse regimes.

### B. Aggressor Flow Gate (afg-f-l8)
- **Mechanism:** Measures signed net aggressor flow (buy volume minus sell volume) over a 10-second rolling window. It skips open legs that enter against the prevailing short-term order flow (e.g., skips a BUY when the tape is dominated by aggressive selling).
- **Performance:** **+972%** Realized PnL vs Baseline.
- **Key Insight:** Avoids immediate adverse selection by respecting revealed directional intent in the recent trade tape.

### C. Vol Regime Sizer (vrs-m-l2)
- **Mechanism:** Continuously scales child order size (via probabilistic submission) inversely proportional to short-term realized mid-price volatility. 
- **Performance:** **+584%** Realized PnL vs Baseline.
- **Key Insight:** A continuous approach that shrinks exposure during microstructure turbulence while maintaining full participation in calm regimes, retaining alpha without the binary risk of skipping entire trades.

## 3. Technical Efficiency: Token Usage & Execution Time

The research experiments were conducted using an agentic loop. Below are representative efficiency metrics for a single research iteration (loop) of each algorithm:

| Algorithm Family      | Avg. Tokens per Loop | Avg. Duration (Seconds) | Avg. Duration (Minutes) |
|-----------------------|----------------------|-------------------------|-------------------------|
| **Position Tier Gate** | ~44,200             | ~693                    | ~11.5                   |
| **Aggressor Flow Gate**| ~41,000             | ~765                    | ~12.7                   |
| **Vol Regime Sizer**   | ~55,200             | ~927                    | ~15.5                   |

*Note: Token usage includes input, output, and cache management (creation/read). Output tokens are typically the smallest component (~1k), with cache management dominating the cost.*

## 4. Required Outputs

Please generate the following materials based on the data above:

### 1. Slide Deck Outline (Text Format)
Provide a 7-slide outline. Each slide should include a **Title**, **Main Bullet Points**, and a description of the **Visual/Chart** that should accompany it.
- **Slide 1:** Title & Objective (Improving noisy oracle execution)
- **Slide 2:** Baseline Issues (Adverse selection, compounding risk)
- **Slide 3:** Solution 1: Position Tier Gate (+2632% PnL)
- **Slide 4:** Solution 2: Aggressor Flow Gate (+972% PnL)
- **Slide 5:** Solution 3: Vol Regime Sizer (+584% PnL)
- **Slide 6:** Technical Efficiency (Token usage vs. Performance)
- **Slide 7:** Summary & Next Steps

### 2. Plotting Requirements (Prompts for Data Viz)
Write detailed prompts or Python script instructions to generate 4 key visualizations:
1. **Cumulative PnL Comparison:** A line chart showing the cumulative realized PnL over the 12-day train window for the Baseline vs. the 3 top algorithms.
2. **Drawdown Over Time:** A chart illustrating how Position Tier Gate caps the severe drawdowns seen in the Baseline.
3. **Trade Count vs. Performance Scatter:** A scatter plot with Trade Count on the X-axis and Realized PnL on the Y-axis to visualize efficiency.
4. **Token Usage vs. PnL Improvement:** A bar or bubble chart showcasing the relationship between "Computational Cost" (Total Tokens) and "Algorithmic Edge" (PnL Improvement %). This should highlight that PTG is not only the most profitable but also one of the most token-efficient solutions.

### 3. Speaker Notes & Executive Summary
Provide a 2-paragraph executive summary that can be read by a non-technical stakeholder, along with bulleted speaker notes for the technical deep-dives on each algorithm and the efficiency metrics.
