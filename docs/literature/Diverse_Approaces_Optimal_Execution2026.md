

# --- DIVERSE APPROACHES TO OPTIMAL EXECUTION SCHEDULE GENERATION ---

A PREPRINT

Robert de Witt\*  
 Imperial College London  
 Bank of America Securities  
 London, United Kingdom  
 robert.de-witt23@imperial.ac.uk  
 robert.de\_witt@bofa.com

Mikko S. Pakkanen  
 Department of Mathematics  
 Imperial College London  
 London, United Kingdom  
 m.pakkanen@imperial.ac.uk

February 2, 2026

## Abstract

We present the first application of MAP-Elites, a quality-diversity algorithm, to trade execution. Rather than searching for a single optimal policy, MAP-Elites generates a diverse portfolio of regime-specialist strategies indexed by liquidity and volatility conditions. Individual specialists achieve 8-10% performance improvements within their behavioural niches, while other cells show degradation, suggesting opportunities for ensemble approaches that combine improved specialists with the baseline PPO policy. Results indicate that quality-diversity methods offer promise for regime-adaptive execution, though substantial computational resources per behavioural cell may be required for robust specialist development across all market conditions.

To ensure experimental integrity, we develop a calibrated Gymnasium environment focused on order scheduling rather than tactical placement decisions. The simulator features a transient impact model with exponential decay and square-root volume scaling, fit to 400+ U.S. equities with  $R^2 > 0.02$  out-of-sample. Within this environment, two Proximal Policy Optimization architectures—both MLP and CNN feature extractors—demonstrate substantial improvements over industry baselines, with the CNN variant achieving 2.13 bps arrival slippage versus 5.23 bps for VWAP on 4,900 out-of-sample orders (\$21B notional). These results validate both the simulation realism and provide strong single-policy baselines for quality-diversity methods.

**Keywords** Optimal Execution · Reinforcement Learning · Market Impact · Transient Impact · Quality-Diversity · MAP-Elites · Algorithmic Trading · Robotics

---

\*The views, opinions and conclusions expressed here are solely those of the authors and do not necessarily reflect the views or policies of the Bank of America, or any other institution with which the authors are affiliated. No responsibility should be attributed to those institutions. This article has not been reviewed, approved, or endorsed by the authors' employers or any affiliated organizations

![Diagram titled 'Optimal Execution' showing the evolution of approaches. Three boxes at the top point to a central box at the bottom. The top-left box is 'Classical Models (e.g., Almgren–Chriss) Mean-variance optimisation, constant volatility, stationary impact'. The top-middle box is 'Empirical Impact Models (e.g., Bouchaud Propagator) Calibrated decay kernel, transient impact, concave scaling'. The top-right box is 'Reinforcement Learning Approaches Agent–environment loop, adaptive policies, simulation-trained'. All three point to a bottom box labeled 'This Work: Novel RL Optimal Execution PPO, MAP-Elites, High-fidelity Gymnasium environment, calibrated transient impact, realistic order generation, vectorised simulation'.](aa9e46d6f962be5cebcbb5c654c9b13e_img.jpg)

```

graph TD
    A[Classical Models  
(e.g., Almgren–Chriss)  
Mean-variance optimisation,  
constant volatility,  
stationary impact] --> B[Empirical Impact Models  
(e.g., Bouchaud Propagator)  
Calibrated decay kernel,  
transient impact,  
concave scaling]
    B --> C[Reinforcement Learning Approaches  
Agent–environment loop,  
adaptive policies,  
simulation-trained]
    A --> D[This Work:  
Novel RL Optimal Execution  
PPO, MAP-Elites, High-fidelity  
Gymnasium environment, calibrated  
transient impact, realistic order  
generation, vectorised simulation]
    B --> D
    C --> D
  
```

Diagram titled 'Optimal Execution' showing the evolution of approaches. Three boxes at the top point to a central box at the bottom. The top-left box is 'Classical Models (e.g., Almgren–Chriss) Mean-variance optimisation, constant volatility, stationary impact'. The top-middle box is 'Empirical Impact Models (e.g., Bouchaud Propagator) Calibrated decay kernel, transient impact, concave scaling'. The top-right box is 'Reinforcement Learning Approaches Agent–environment loop, adaptive policies, simulation-trained'. All three point to a bottom box labeled 'This Work: Novel RL Optimal Execution PPO, MAP-Elites, High-fidelity Gymnasium environment, calibrated transient impact, realistic order generation, vectorised simulation'.

Figure 1: Evolution of optimal execution approaches: from classical models to empirical impact models to reinforcement learning, with this work positioned at the intersection of empirically calibrated models and RL methods.

## 1 Introduction

Optimal execution (OE) is a central problem in algorithmic trading, influencing approximately a trillion dollars of daily turnover across global equities and futures markets. It concerns determining how to trade a given order over a predetermined or dynamic horizon while minimising transaction costs relative to a benchmark, typically the *arrival price*—the mid-quote at the time the order is initiated. This performance is often expressed as *implementation shortfall* (Perold, 1988), the difference between the value of an ideally priced portfolio and the actual cost of implementing it through trading. Transaction costs arise from explicit sources (e.g., commissions and fees) and implicit sources (e.g., market impact and slippage). The execution challenge is compounded by the stochastic nature of prices, variable liquidity conditions, and the trade-off between market impact and timing risk (Almgren and Chriss, 2001).

The evolution of optimal execution approaches is outlined in Figure 1. Traditional approaches, such as the seminal Almgren–Chriss framework, cast the execution problem as a mean-variance optimisation in which market impact is modelled as an additive cost and risk is penalised via price variance. While yielding tractable closed-form schedules (e.g., linear, front-loaded, or back-loaded trajectories), these models assume constant volatility, stationary impact functions, and exogenous order flow (Almgren and Chriss, 2001; Obizhaeva and Wang, 2013). Empirical studies show that market impact scales concavely with order size and decays transiently over time (Bouchaud, 2010; Bouchaud et al., 2018), motivating richer dynamic models.

In recent years, alongside other data-driven approaches, reinforcement learning (RL) has emerged as a promising alternative for OE (Nevmyvaka et al., 2006; Hendricks and Wilcox, 2014). RL agents can learn adaptive policies that respond to evolving market states without assuming explicit parametric forms for price dynamics or impact decay. The agent–environment loop in Gymnasium (Towers et al., 2024) offers a natural abstraction: the agent observes the current market state (e.g., prices, volumes, volatility, time remaining, inventory) and outputs an action representing a trade size or participation rate. The environment then simulates execution, applies market impact, updates the state, and returns a reward signal tied to execution performance. This process enables the agent to learn policies through simulation without incurring the

cost and risk of live experimentation; once deployed, such policies can be further adapted using live trading outcomes.

However, much of the existing RL literature for OE suffers from limited realism in backtesting. Many implementations use oversimplified price dynamics (e.g., geometric Brownian motion) or neglect empirically calibrated market impact, while others focus on highly granular limit order book (LOB) simulations that require many structural assumptions and can diverge from practical execution workflows. This paper takes a middle path, avoiding both coarse-grained price-only models and overly complex LOB simulations. It builds a high-fidelity Gymnasium-based back-testing environment calibrated to one year of historical minute-bar data for hundreds of US equities. The environment integrates a transient market impact model fit via cross-validation, realistic order-arrival processes, and configurable state/reward designs, enabling a robust evaluation of RL and baseline strategies.

We utilise this environment to train RL policies designed to decide how much to trade at any point in an order’s lifespan. The generated policy is not concerned with what limit price, type, or venue to use, but rather the schedule of quantities to trade, given a reward-driven objective. With the right reward structure and cost function, this approach could, in principle, generalise beyond volume-weighted average price (VWAP) to improve upon present-day execution schedules such as time-weighted average price (TWAP), percentage of volume (POV), implementation shortfall, or liquidity-seeking strategies. We focus on an optimised VWAP structure which aims to reduce slippage to the order arrival price by allowing some discretion to a base VWAP schedule. We choose this as an initial approach as there are immediate large-scale applications for an optimally performing scheduler. This structure greatly simplifies the action space of the RL algorithm while opening up flexibility for a highly informative state space to act on, increasing the likelihood of superior decisions can be learned in simulation.

A key limitation of existing RL approaches to execution is that they optimise for a single policy maximizing average performance across all market conditions. Quality-diversity (QD) algorithms (Chatziloygeroudis et al., 2021), developed originally for adaptive robotics, offer an alternative paradigm. Rather than searching for a single optimum, QD methods such as MAP-Elites (Mouret and Clune, 2015) generate portfolios of high-performing policies, each specialised for different behavioural niches defined by descriptor features. In robotics, these descriptors might characterise terrain type or gait stability; in optimal execution, natural descriptors include market regime (volatility, liquidity), order urgency, or directional momentum. We apply MAP-Elites using liquidity and volatility as behavioural descriptors to generate regime-specialist execution policies. To our knowledge, this is the first application of quality-diversity methods to the optimal execution problem.

The contributions of this work are:

1. **First application of quality-diversity methods to financial execution.** We apply MAP-Elites to generate portfolios of regime-specialist execution policies indexed by liquidity-volatility descriptors. While individual specialists achieve 8-10% improvements in specific niches, results reveal challenges in regime classification and training data density that motivate future research. To our knowledge, this is the first exploration of quality-diversity algorithms for trading.
2. **Validation of RL under empirically calibrated transient impact.** Using a propagator model with exponential decay and square-root scaling ( $R^2 > 0.02$  out-of-sample), we demonstrate PPO-CNN achieves 59% lower arrival slippage than VWAP (2.13 vs 5.23 bps) on \$21B test set. This establishes both a strong baseline for quality-diversity methods and validates that RL can exceed industry benchmarks under realistic impact dynamics.
3. **GEO: Open-source environment enabling reproducible execution research.** We plan to release a calibrated Gymnasium simulator with realistic order generation, minute-bar execution, and transient impact modeling. This infrastructure enables fair comparison of execution algorithms and supports future quality-diversity research.

The remainder of this paper is structured as follows. Section 2 introduces the problem formulation and proposed solutions. We begin with the optimal execution set-up, including the formal problem statement, the transient impact model with its calibration, and the construction of raw and derived features. We then introduce reinforcement learning, translating OE into the RL framework and outlining the order generation process. Next, we present the RL methods explored, covering architecture variations (MLP and CNN) of Proximal Policy Optimisation (PPO) and Quality-Diversity approaches (MAP-Elites) and industry-standard execution strategies. Finally, we describe how these components fit into the simulation environment design, including Gymnasium integration and the execution simulator with impact. Section 3 reports the impact

model calibration results and compares the performance of the RL agents against standard benchmarks. Section 4 concludes with implications of our findings, limitations of the framework, and potential directions for future research.

## 2 Methods

### 2.1 Optimal Execution Problem Set-up

#### 2.1.1 Fundamental OE problem formulation

We consider the execution of a single parent order of size  $Q_0$  shares over a fixed horizon of  $H$  discrete time steps, each corresponding to one minute of market time. The order size  $Q_0$ , horizon  $H$ , and stock  $S_0$  are specified by the portfolio manager. While one could also consider continuous or event-driven time-steps, for simplicity we work with minute-binned outcomes.

The objective is to minimise the *implementation shortfall* (IS) relative to the mid-price  $(p_{\text{bid}} + p_{\text{ask}})/2$  at the start of the order,  $p_0$ :

$$\text{IS} = \text{side} \times \left( \frac{\sum_{t=0}^{H-1} p_t^{\text{fill}} \cdot |q_t|}{Q_0} - p_0 \right),$$

where  $\text{side} \in \{+1, -1\}$  indicates a buy or sell order, and  $q_t$  is the signed quantity traded at time  $t$  at the price  $p_t^{\text{fill}}$ . This expression is equivalent to the realised VWAP of the executed order minus the benchmark price, scaled by trade direction.

The realised fill price, in reality, is the volume weighted average price (VWAP) of the shares traded in the market. In simulation,  $p_t^{\text{fill}}$  incorporates both the prevailing historical market VWAP and the total price impact  $I_t$  (immediate plus propagated) generated by the trade. Here  $I_t$  is modelled through the transient propagator framework (Bouchaud et al., 2018), detailed in Section 2.1.2. Incorporating such impact-adjusted fills is one of the key differentiators of this work to ensure realism when training our models.

Since the arrival price is only a single point in time benchmark, to better measure our execution efficiency within the horizon  $H$ , we also consider a second benchmark for robustness: slippage relative to market VWAP

$$P^{\text{VWAP}} = \frac{\sum_{t=0}^{H-1} v_t p_t}{\sum_{t=0}^{H-1} v_t},$$

where  $v_t$  is traded volume and  $p_t$  is the filled price at time  $t$ .

#### 2.1.2 Propagator Model (Transient Impact Model)

As with all reinforcement learning policy optimisations, the realism of the simulation environment directly impacts the quality of the learned action policy. If the simulation dynamics diverge materially from the “physical laws” governing markets, then the resulting strategies will be suboptimal when deployed. While exchange microstructure rules can be simulated with reasonable fidelity, modelling the impact of incremental orders on market prices at one-minute granularity is far more challenging. Fortunately, thanks to the work of Bouchaud (2010); Bouchaud et al. (2018); Obizhaeva and Wang (2013); Gatheral et al. (2012), the *propagator model* provides a tractable framework to capture transient market impact. This formulation allows the impact of each executed trade to propagate forward in time with a decaying influence on prices. Given our one-minute granularity, where there may be intermittent gaps, we find the transient impact model with an *exponential decay kernel* to be the most suitable for simulation.

**General formulation.** Let  $\epsilon_t \in \{+1, -1\}$  denote the trade sign (buy or sell),  $q_t$  the agent’s traded quantity, and  $V_t$  the market volume at time  $t$ . The return at time  $t$  is modelled as

$$r_t = \sum_{\ell=1}^L G(\ell) f(q_{t-\ell}, V_{t-\ell}) \epsilon_{t-\ell} + \eta_t, \quad (1)$$

where  $G(\ell)$  is the propagator kernel describing how impact at lag  $\ell$  decays over time,  $f(q, V)$  is the instantaneous impact function, and  $\eta_t$  is exogenous noise.

![Figure 2: A plot showing three transient impact kernels over a lag of 0 to 30 minutes. The y-axis is 'Impact [bps]' ranging from 0 to 1. The x-axis is 'lag l (minutes)' ranging from 0 to 30. The legend indicates: a dashed line for 'Exponential: e^{-l/\tau}', a dotted line for 'Power law: (l + l_0)^{-\gamma}', and a solid black dot at (0, 1) for 'Instantaneous: \delta(l) (schematic)'. The exponential kernel decays rapidly, while the power-law kernel decays more slowly, showing a long tail.](7a3561af571faf036baa93f5f4b1bdb9_img.jpg)

Figure 2: A plot showing three transient impact kernels over a lag of 0 to 30 minutes. The y-axis is 'Impact [bps]' ranging from 0 to 1. The x-axis is 'lag l (minutes)' ranging from 0 to 30. The legend indicates: a dashed line for 'Exponential: e^{-l/\tau}', a dotted line for 'Power law: (l + l\_0)^{-\gamma}', and a solid black dot at (0, 1) for 'Instantaneous: \delta(l) (schematic)'. The exponential kernel decays rapidly, while the power-law kernel decays more slowly, showing a long tail.

Figure 2: Illustrative transient impact kernels in basis points. The instantaneous kernel is shown schematically as a unit impulse; exponential and power-law forms capture transient, decaying impact with different memory.

The cumulative transient impact  $I_t$ , which shifts the fill prices in the execution simulator (cf. Section 2.1), is then

$$I_t = \sum_{\ell=1}^L G(\ell) f(v_{t-\ell}) \epsilon_{t-\ell}.$$

**Instantaneous impact.** The instantaneous impact function scales as a power law in the participation rate:

$$f(q, V) = \gamma \left( \frac{q}{V} \right)^\beta, \quad \beta \in (0, 1),$$

where  $\gamma$  is a stock- and regime-dependent scale factor, and  $\beta$  typically lies between 0.4 and 0.7 for equities. This concavity captures the empirically observed “square-root law” of market impact. At the shortest time scales, however, the impact function is often observed to be closer to linear. For example, Cont et al. (2014) show that short-horizon price changes are linearly related to order flow imbalance, Tóth et al. (2011) find an additive linear response kernel across traders, and Bucci et al. (2019) document a crossover regime between linear and square-root impact. In Section 3, we empirically compare both functional forms at the one-minute horizon, finding that the square-root law provides superior explanatory power ( $R^2$ ) in our dataset.

**Propagator kernel.** As illustrated in Figure 2, the choice of kernel  $G(\ell)$  determines how quickly past trades lose their influence on current prices. Empirical studies show that impact is neither permanent (constant  $G(\ell)$ ) nor purely instantaneous (delta kernel), but decays gradually over time. Several functional forms have been proposed, including power-law kernels (Bouchaud, 2010) and stretched exponentials (Mastromatteo et al., 2014).

In this work, we adopt the exponential kernel

$$G(\ell) = G_0 e^{-\ell/\tau},$$

where  $G_0$  is the immediate impact coefficient,  $\ell$  is the time since the last trade and  $\tau$  is the characteristic decay horizon in minutes. This form balances tractability with fidelity: it ensures that impact is transient, avoids long-memory tails that can destabilise calibration on finite samples, and is consistent with empirical fits of minute-bar data. The exponential kernel also integrates naturally with reinforcement learning by ensuring a well-behaved, Markovian state evolution.

**Summary.** Combining the exponential kernel with the power-law impact function yields the full transient impact model:

$$I_t = \sum_{\ell=1}^L G_0 e^{-\ell/\tau} \gamma \left( \frac{q_{t-\ell}}{V_{t-\ell}} \right)^\beta \epsilon_{t-\ell},$$

which adjusts fill prices according to:

$$p_t^{\text{fill}} = p_t^{\text{VWAP}} (1 + \text{side} \cdot I_t).$$

![Figure 3: Classic RL Flow diagram. The diagram shows a loop between an 'Agent' (purple oval) and an 'Environment' (green oval). The Agent sends an 'Action' (a_t) to the Environment. The Environment returns a 'Reward' (r_t) and a 'New state' (s_{t+1}) to the Agent. The Agent also receives the 'State' (s_t) from the Environment. The flow is: Agent -> Action -> Environment -> New state -> State -> Agent.](a7d78d22e465dea388b31d0739f9d0cd_img.jpg)

```

graph TD
    Agent((Agent)) -- Action a_t --> Env((Environment))
    Env -- "New state s_{t+1}" --> State
    State -- "State s_t" --> Agent
    Env -- Reward r_t --> Agent
  
```

Figure 3: Classic RL Flow diagram. The diagram shows a loop between an 'Agent' (purple oval) and an 'Environment' (green oval). The Agent sends an 'Action' (a\_t) to the Environment. The Environment returns a 'Reward' (r\_t) and a 'New state' (s\_{t+1}) to the Agent. The Agent also receives the 'State' (s\_t) from the Environment. The flow is: Agent -> Action -> Environment -> New state -> State -> Agent.

Figure 3: Classic RL Flow diagram, adapted from Sutton and Barto (2018).

This formulation arises naturally from resilience models (Obizhaeva and Wang, 2013), where impact decays as  $\hat{I}(t) = -\frac{1}{\tau}I(t) + \kappa\hat{Q}(t)$ . Gatheral et al. (2012) showed that admissible (non-manipulable) kernels must be completely monotone—i.e., mixtures of exponentials—further justifying this choice. While Bouchaud’s propagator framework (Bouchaud et al., 2018) often employs power-law kernels, the exponential form offers a tractable Markovian approximation that calibrates well at minute-bar horizons.

### 2.2 Reinforcement Learning Models

We investigate several reinforcement learning (RL) approaches as candidates for improving execution performance beyond traditional benchmark methods such as TWAP, VWAP, and POV. Our analysis begins with variations of Proximal Policy Optimisation (PPO) (Schulman et al., 2017), a widely adopted and robust policy-gradient algorithm that has become a standard baseline in sequential decision-making. Building on this foundation, we extend our study to a more exploratory direction: MAP-Elites (Mouret and Clune, 2015), a quality-diversity algorithm designed to promote behavioural diversity while retaining high-performing strategies. To the best of our knowledge, MAP-Elites has not previously been applied to optimal execution, making its evaluation in this setting a novel contribution of our work.

#### 2.2.1 RL Fundamentals

Reinforcement Learning (RL) is a framework for sequential decision-making in which an agent interacts with an environment in order to maximise cumulative reward (Sutton and Barto, 2018). As shown in Figure 3, at each discrete time step  $t$ , the environment is described by a *state*  $s_t \in \mathcal{S}$  that captures the relevant features observable by the agent. In the context of execution, this state might include remaining inventory, elapsed time, spreads, volatility, imbalance, recent trade volumes, prices, or other relevant market information.

The agent selects an *action*  $a_t \in \mathcal{A}$ , which in execution corresponds to how much of the parent order to trade in the next step (for example, a fraction of the current market volume or a deviation from a baseline schedule). The environment responds by transitioning to a new state  $s_{t+1}$  and producing a scalar *reward*  $r_t \in \mathbb{R}$ , which evaluates the quality of the action taken. In execution, rewards are typically designed as the negative of slippage, transaction cost, or schedule deviation, so that higher returns correspond to better execution quality.

A full sequence of states, actions, and rewards is called a *trajectory*,

$$\tau = (s_0, a_0, r_0, s_1, a_1, r_1, \dots, s_H),$$

with horizon  $H$  corresponding to the lifetime of an order. In execution, one trajectory corresponds to a complete order being executed from start to finish.

The objective of RL is to maximise the expected *return*  $G_t$ , defined as the discounted sum of future rewards:

$$G_t = \sum_{k=0}^{\infty} \gamma^k r_{t+k},$$

where the *discount factor*  $\gamma \in [0, 1]$  determines how much future rewards influence present decisions. In execution, setting  $\gamma$  close to 1 ensures that the agent considers the long-term cost of completing an order, while smaller values of  $\gamma$  emphasise immediate trading costs.

The expected return under policy  $\pi$  can be described using a *value function*,

$$V^\pi(s) = \mathbb{E}[G_t \mid s_t = s, \pi],$$

which measures the expected execution quality from state  $s$ . More generally, the *action-value function* quantifies the return of taking action  $a$  in state  $s$  and then following  $\pi$  thereafter:

$$Q^\pi(s, a) = \mathbb{E}[G_t \mid s_t = s, a_t = a, \pi].$$

The *advantage function* refines this by comparing the value of a particular action to the state average:

$$A^\pi(s, a) = Q^\pi(s, a) - V^\pi(s).$$

In execution, the advantage can be interpreted as whether trading faster or slower than usual at a given state improves performance.

A common challenge in estimating advantages is the high variance of Monte Carlo returns. To mitigate this, Schulman et al. (2016) introduced *Generalised Advantage Estimation (GAE)*, which mixes  $n$ -step temporal-difference residuals with an exponentially decaying weight  $\lambda \in [0, 1]$ . GAE defines the advantage estimate as:

$$\hat{A}_t^{\text{GAE}(\gamma, \lambda)} = \sum_{l=0}^{\infty} (\gamma \lambda)^l \delta_{t+l}^V, \quad \delta_t^V = r_t + \gamma V(s_{t+1}) - V(s_t),$$

where  $\delta_t^V$  is the one-step temporal-difference (TD) error. Lower values of  $\lambda$  reduce variance by relying more on shorter-horizon TD estimates, while higher values reduce bias by incorporating longer returns. Proximal Policy Optimisation (PPO) (Schulman et al., 2017) commonly employs GAE with  $\lambda \approx 0.95$  to stabilise training, providing a robust trade-off between bias and variance.

PPO belongs to the family of *actor-critic* methods, where two neural networks are trained jointly:

- The **actor** represents the policy  $\pi_\theta(a|s)$ , which outputs a distribution over actions given the current state. In execution, this determines how aggressively to trade at each step.
- The **critic** estimates the value function  $V_\phi(s)$ , parameterised by  $\phi$ , which predicts the expected return from state  $s$ .

The critic serves as a baseline for advantage estimation, reducing variance in policy-gradient updates. Concretely, the policy gradient is estimated as

$$\nabla_\theta J(\theta) \approx \mathbb{E}_t \left[ \nabla_\theta \log \pi_\theta(a_t|s_t) \hat{A}_t \right],$$

where  $\hat{A}_t$  is provided by GAE. The critic’s role is to supply  $V^\pi(s_t)$  in the advantage calculation, thereby reducing variance compared to pure Monte Carlo returns. This actor-critic loop ensures that PPO can adaptively balance exploration of new execution strategies with exploitation of known good policies.

PPO is particularly well-suited for execution problems. Unlike off-policy methods, e.g., deep Q networks (DQN) and soft actor-critic (SAC), that can reuse historical data, PPO is on-policy, meaning it learns only from trajectories generated by its current policy. While this reduces sample efficiency, it provides more stable learning in non-stationary environments where market conditions shift. The clipped objective (detailed in Section 2.4.1) prevents destructively large policy updates that could catastrophically degrade execution performance. For execution, where a bad policy update could mean significant losses if deployed, PPO’s conservative update mechanism is a significant advantage in ensuring stable progress towards an improved policy.

### 2.3 Gymnasium for Executing Optimally (GEO)

#### 2.3.1 Data: Minute Bar Data

Our back-testing environment is calibrated using minute-bar data from approximately 400 US equities sourced from Mana Tech (Mana Tech LLC, 2025) for the entirety of the year 2022. Each bar contains bid/ask/mid quotes and displayed depth, trade prices, sided and hidden volumes, among other features. For each symbol and trading day, the dataset provides the variables listed in Table 3 (in Appendix A).

Data cleaning steps include forward-filling missing quotes (at most one bar), excluding minute intervals with no reported trades when constructing returns, and filtering extreme return outliers. Stocks with more than 7% missing values were removed to avoid instability. Summary statistics of the resulting dataset are shown in Figure 15 (in Appendix A).

![Figure 4: Schematic overview of the GEO environment architecture. The diagram shows a flow from Data Ingestion & Storage to Analytics & Labels to Order Generation to Model Training. Analytics & Labels also feeds into the Gymnasium Environment. The Gymnasium Environment feeds into Agents (PPO-MLP (SB3), PPO-CNN (SB3), MAP-Elites (quality-diversity)). Agents feed into Testing / Inference. Model Training feeds into Propagator-Based Simulation, which feeds into Testing / Inference. Testing / Inference feeds into Model Registry TensorBoard.](990567efebf979be51f56d1150012c9d_img.jpg)

```

graph TD
    A[Data Ingestion & Storage] --> B[Analytics & Labels]
    B --> C[Order Generation]
    B --> D[Gymnasium Environment]
    C --> E[Model Training]
    E --> F[Propagator-Based Simulation]
    F --> G[Testing / Inference]
    D --> H[Agents]
    H --> G
    G --> I[Model Registry TensorBoard]
  
```

Figure 4: Schematic overview of the GEO environment architecture. The diagram shows a flow from Data Ingestion & Storage to Analytics & Labels to Order Generation to Model Training. Analytics & Labels also feeds into the Gymnasium Environment. The Gymnasium Environment feeds into Agents (PPO-MLP (SB3), PPO-CNN (SB3), MAP-Elites (quality-diversity)). Agents feed into Testing / Inference. Model Training feeds into Propagator-Based Simulation, which feeds into Testing / Inference. Testing / Inference feeds into Model Registry TensorBoard.

Figure 4: Schematic overview of the GEO environment architecture, showing the interaction between agent, environment, and calibrated market impact model.

#### 2.3.2 Daily Analytics

From the one-minute level data we construct a set of daily statistics to be used by GEO and by the learning models. These include averages of daily trading volume, spreads, order book depth, and trade count, as well as Parkinson (1980) high-low volatility estimates, defined as

$$\hat{\sigma}_d^{(n)} = \sqrt{\frac{1}{4n \ln 2} \sum_{i=0}^{n-1} [\ln(P_{d-i}^H/P_{d-i}^L)]^2},$$

over 1-, 2-, and 5-day windows, where intraday high-low ranges are used to provide robust volatility estimates less sensitive to bid-ask bounce than close-to-close returns. Detailed definitions of these features are provided in Appendix A, Table 4.

#### 2.3.3 Environment Design and Gymnasium Integration

The *GEO* backtest environment (Figure 4) is implemented as a custom Gymnasium environment that adheres to the Gymnasium API (Towers et al., 2024; Ray Team, 2025; Stable-Baselines3 Developers, 2025), enabling seamless integration with a wide range of RL algorithms. The design follows three principles:

- (i) *realism*, achieved through historical data-driven calibration of impact and volatility;
- (ii) *modularity*, enabling easy swapping of components such as reward functions or impact models; and
- (iii) *compatibility*, ensuring adherence to Gym’s `reset()` and `step()` interface.

Prior researchers have used Gymnasium in simulators such as *ABIDES* and *mbt\_gym*, though their focus has largely been on limit order book (LOB) dynamics (Jerome et al., 2023; Amrouni et al., 2022; Hafsi and Vittori, 2024). In contrast, our framework targets execution at the minute-bar horizon with transient market impact.

The core environment extends Gymnasium’s `Env` class and supports vectorised execution for efficient parallel simulation of multiple orders, utilising multiple core CPU acceleration. Each episode corresponds to the execution of a single parent order over  $H$  time steps, with each step representing one minute of market time.

The RL execution agent begins from a baseline schedule, defined as a target percentage of expected market volume, and modifies this on a minute-by-minute basis. This design ensures the order is always completed by the horizon  $H$ . At each step, the agent chooses an action  $a_t$  that scales the baseline participation rate up or down. Negative values slow execution, while positive values accelerate it, with  $a_t = -1$  corresponding to no trading in that step.

##### Action space:

$$a \in \{-1, -0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75, 1\}$$

This discrete action space simplifies exploration while providing sufficient granularity for adaptive scheduling. The symmetric range around zero allows both acceleration ( $a_t > 0$ ) and deceleration ( $a_t < 0$ ) from the baseline rate, with  $a_t = -1$  pausing execution for the current step.

##### Target rate with action:

$$\rho_t^{\text{action}} = \rho_t^{\text{target}} \cdot (1 + a_t), \quad \rho_t^{\text{target}} = \frac{q_t^{\text{rem}}}{\mathbb{E}[V_{t,H}]},$$

where  $q_t^{\text{rem}} = Q_0 - \sum_{i=0}^t q_i$  is the remaining inventory at step  $t$ , and  $\mathbb{E}[V_{t,H}]$  is the expected remaining market volume over the interval  $[t, H]$ . The executed quantity is then

$$q_t = \rho_t^{\text{action}} \cdot V_t^{\text{market}}.$$

The environment tracks remaining quantity, elapsed time, arrival slippage, VWAP slippage, holding cost, impact-adjusted fill prices and accumulated impact. State transitions are driven jointly by the agent's actions and exogenous price changes from historical data. The agent observes a 13-dimensional feature vector  $\mathbf{o}_t \in \mathbb{R}^{13}$  at each timestep, comprising market state, execution progress, impact metrics, and regime context:

$$\mathbf{o}_t = \begin{bmatrix} p_t^{\text{mid}}, & V_t, & H - t, & q_t^{\text{rem}}, & \text{ADV}\%, & \text{EHV}\%, \\ p_{t-1}^{\text{fill}}, & q_{t-1}, & I_t^{\text{imm}}, & I_t^{\text{cum}}, & & \\ p^{\text{arrival}}, & \sigma^{(1)}, & \sigma^{(5)}, & & & \end{bmatrix}^T$$

where  $p_t^{\text{mid}}$  is the current mid-price,  $V_t$  is market volume at time  $t$ ,  $H - t$  is remaining time steps,  $q_t^{\text{rem}}$  is remaining inventory,  $\text{ADV}\%$  and  $\text{EHV}\%$  are order size relative to average daily volume and expected horizon volume,  $p_{t-1}^{\text{fill}}$  and  $q_{t-1}$  capture the most recent trade,  $I_t^{\text{imm}}$  and  $I_t^{\text{cum}}$  are immediate and accumulated impact costs (in basis points),  $p^{\text{arrival}}$  is the order arrival benchmark, and  $\sigma^{(1)}, \sigma^{(5)}$  are 1-day and 5-day Parkinson volatility estimates.

#### 2.3.4 Order Generation

Orders are generated using an order generator inside GEO, which samples from historical order flow characteristics to produce a diverse set of parent orders. Each order is parameterised by:

- **Symbol and date**, drawn from the historical dataset.
- **Time horizon**, randomly sampled between 1 and 390 minutes (up to a full trading day).
- **Order size**, expressed as a percentage of expected horizon volume (EHV), sampled from a configurable distribution to simulate varying levels of urgency.
- **Side** (+1 for buy, -1 for sell), chosen with equal probability.

This sampling procedure produces a heterogeneous set of parent orders that vary in size, duration, and liquidity environment, thereby exposing the agent to a broad distribution of execution scenarios. The training dataset is drawn from a historical period strictly preceding the test dataset, ensuring that evaluation is performed under market conditions not encountered during training. This split allows a fair out-of-sample assessment of generalisation performance.

In this project, we use nine months of trading data for training and three months for testing, across the universe in the minute bar dataset defined in Section 2.3.1. An illustration of the resulting order size and horizon distributions is provided in Figure 5.

![Figure 5: Sample set of generated orders with impact and decay coefficients, stratified by symbol, size, and time horizon. The figure contains nine subplots: 1. Order Size Distribution: Histogram of order sizes (0.0 to 2.5e6) for Train (blue) and Test (purple) sets. 2. Time Horizon Distribution: Histogram of time horizons in minutes (0 to 400) for Train (blue) and Test (purple) sets. 3. ADV Percentage Distribution: Histogram of ADV percentage (0.00 to 0.10) for Train (blue) and Test (purple) sets. 4. Daily Volatility by Month: Box plots of daily volatility (0.01 to 0.05) by month from 2022-01 to 2022-12 for Train (blue) and Test (purple) sets. 5. Daily Volatility Distribution: Histogram of daily volatility (0.01 to 0.05) for Train (blue) and Test (purple) sets. 6. Intra-order Return Distribution: Histogram of intra-order returns (-0.10 to 0.30) for Train (blue) and Test (purple) sets. 7. Y Values Distribution (Impact Coefficient): Histogram of impact coefficients (0.00000 to 0.00072) for Train (blue) and Test (purple) sets. 8. Tau Values Distribution (Decay Rate): Histogram of decay rates (0 to 180) for Train (blue) and Test (purple) sets. 9. ADV Percentage by Date (Mean ± Standard Error): Line plot of ADV percentage (%) over time (2022-01-08 to 2023-01-03) for Train (blue) and Test (purple) sets.](7801d00a216dc4dc8a7d210dcb5fe3c5_img.jpg)

Figure 5: Sample set of generated orders with impact and decay coefficients, stratified by symbol, size, and time horizon. The figure contains nine subplots: 1. Order Size Distribution: Histogram of order sizes (0.0 to 2.5e6) for Train (blue) and Test (purple) sets. 2. Time Horizon Distribution: Histogram of time horizons in minutes (0 to 400) for Train (blue) and Test (purple) sets. 3. ADV Percentage Distribution: Histogram of ADV percentage (0.00 to 0.10) for Train (blue) and Test (purple) sets. 4. Daily Volatility by Month: Box plots of daily volatility (0.01 to 0.05) by month from 2022-01 to 2022-12 for Train (blue) and Test (purple) sets. 5. Daily Volatility Distribution: Histogram of daily volatility (0.01 to 0.05) for Train (blue) and Test (purple) sets. 6. Intra-order Return Distribution: Histogram of intra-order returns (-0.10 to 0.30) for Train (blue) and Test (purple) sets. 7. Y Values Distribution (Impact Coefficient): Histogram of impact coefficients (0.00000 to 0.00072) for Train (blue) and Test (purple) sets. 8. Tau Values Distribution (Decay Rate): Histogram of decay rates (0 to 180) for Train (blue) and Test (purple) sets. 9. ADV Percentage by Date (Mean ± Standard Error): Line plot of ADV percentage (%) over time (2022-01-08 to 2023-01-03) for Train (blue) and Test (purple) sets.

Figure 5: Sample set of generated orders with impact and decay coefficients, stratified by symbol, size, and time horizon.

#### 2.3.5 Execution Simulation

At each step  $t$ , the agent selects an action  $a_t$  that scales the baseline participation rate to determine trade size  $q_t$ , which is then executed at impact-adjusted prices using the transient impact framework (Section 2.1.2). The remaining inventory evolves as

$$q_t^{\text{rem}} = Q_0 - \sum_{i=0}^{t-1} q_i,$$

and the executed quantity in step  $t$  is

$$q_t = (1 + a_t) \frac{q_t^{\text{rem}}}{\mathbb{E}[V_{t,H}]} V_t^{\text{market}},$$

which ensures that the order is fully completed by the horizon  $H$ .

The execution price is then determined using the propagator model. Specifically, fills are taken at the contemporaneous market VWAP shifted by the cumulative transient impact  $I_t$  from current and past trades:

$$p_t^{\text{fill}} = p_t^{\text{VWAP}} (1 + \text{side} \cdot I_t),$$

where  $\text{side} \in \{+1, -1\}$  indicates buy or sell.

The environment records both the impact-adjusted execution price  $p_t^{\text{fill}}$  and the realised implementation shortfall at each step, enabling post-hoc analysis of execution quality and fair comparison across policies. Impact model parameters  $(\gamma, G_0, \tau)$  are pre-calibrated per stock (Section 3.1) and assigned to orders based on their symbol, ensuring consistent dynamics across training and evaluation.

#### 2.3.6 Reward Function

The agent's reward is the negative of a weighted sum of execution costs:

$$r_t = -(\beta_1 C_{\text{arrival}} + \beta_2 C_{\text{VWAP,spread}} + \beta_3 \Delta + \beta_4 \zeta),$$

where  $\beta_1, \dots, \beta_4$  are researcher-defined weights that reflect the relative priority of each objective. In our experiments,  $\beta_{1..4}$  are weights reflecting objective priorities. We set  $\beta_1 = \beta_2 = \beta_3 = 1.0$  and  $\beta_4 = 0.1$ , emphasizing slippage minimization (arrival and VWAP) and schedule adherence while applying a smaller weight to the completion penalty for numerical balance.

##### Arrival slippage $C_{\text{arrival}}$

$$C_{\text{arrival}} = \text{side} \left( \frac{\sum_{\tau=0}^t p_{\tau}^{\text{fill}} |q_{\tau}|}{\sum_{\tau=0}^t |q_{\tau}|} - p_0 \right).$$

Execution shortfall vs. arrival mid-price  $p_0$ .

##### VWAP slippage $C_{\text{VWAP}}$

$$C_{\text{VWAP}} = \text{side} \left( \frac{\sum_{\tau=0}^t (p_{\tau}^{\text{fill}}) |q_{\tau}|}{\sum_{\tau=0}^t |q_{\tau}|} - P^{\text{VWAP}} \right).$$

VWAP slippage allows us to measure execution efficiency.

##### Schedule Deviation $\Delta$

$$\Delta = \sigma_{\text{minute}} \frac{|\rho_{\text{actual}} - \rho_{\text{target}}|}{\rho_{\text{target}}}.$$

Volatility-scaled penalty for departing from the target participation rate, where  $\sigma_{\text{minute}}$  is the per-minute volatility estimate, computed as  $\sigma_{\text{daily}}/\sqrt{390}$  using daily Parkinson volatility.

##### **Completion penalty $\zeta$**

$$\zeta = \sigma_{\text{minute}} \frac{q_{\text{rem}}}{Q_0}.$$

Discourages unfinished inventory; proportional to  $q_{\text{rem}}$  and market turbulence.

A negative slippage (buying below the benchmark for buys, or selling above it for sells) contributes positively to the reward via the sign in  $C_{\text{arrival}}$  and  $C_{\text{VWAP,spread}}$ .

#### **2.3.7 Baseline Strategies**

We construct a set of standard baseline strategies to benchmark the experimental agents against. The implementations for TWAP, VWAP, and POV emulate common execution algorithms, providing realistic reference points. A purely random policy is also included as a noise-driven comparator.

##### **TWAP – Time-Weighted**

$$q_t^{\text{TWAP}} = \frac{Q_0}{H}.$$

Constant shares each minute.

##### **VWAP – Volume-weighted**

$$q_t^{\text{VWAP}} = Q_0 \cdot \frac{\bar{V}_t}{\sum_{\tau=0}^{H-1} \bar{V}_\tau}.$$

Allocate proportionally to historical intraday volume profile  $\bar{V}_t$ , where  $\bar{V}_t$  is the average market volume at minute  $t$  over the past  $N$  trading days.

##### **POV – Percentage of Volume**

$$q_t^{\text{POV}} = \rho_{\text{target}} V_t, \quad \rho_{\text{target}} = \frac{Q_0}{\sum_{\tau=0}^{H-1} \bar{V}_\tau}.$$

Trade a fixed participation of *realised* market volume  $V_t$ ;  $\rho_{\text{target}}$  chosen to complete in expectation over  $H$  based on historical volume  $\bar{V}[a, H]$ .

##### **Random – Noise baseline**

At each minute draw  $a_t$  from the action set and set

$$q_t^{\text{RAND}} = (1 + a_t) \frac{q_t^{\text{em}}}{\mathbb{E}[V_t, H]} V_t, \quad q_t^{\text{em}} = Q_0 - \sum_{i=0}^{t-1} q_i.$$

so completion is still enforced by the target-rate scaffolding.

All baselines are evaluated within the GEO environment using the same calibrated transient impact model and fill price mechanism as the RL agents, ensuring fair comparison. Each baseline executes orders according to its deterministic schedule, with fills adjusted for market impact via Equation (1).

### **2.4 Novel RL Approaches to Optimal Execution**

#### **2.4.1 Proximal Policy Optimisation models (PPO)**

PPO belongs to the family of *policy-gradient methods*, which directly optimise a parametrised policy  $\pi_\theta(a|s)$  by estimating gradients of the expected return with respect to the parameters  $\theta$ . Unlike value-based methods such as Q-learning, which learn an action-value function  $Q(s, a)$  and act greedily via  $\arg \max_a Q(s, a)$ , policy-gradient methods adjust  $\pi_\theta$  itself to increase the probability of selecting actions that yield higher returns.

Formally,

$$\nabla_{\theta} J(\pi_{\theta}) = \mathbb{E}_{s_t \sim d^{\pi_{\theta}}, a_t \sim \pi_{\theta}} [\nabla_{\theta} \log \pi_{\theta}(a_t | s_t) Q^{\pi_{\theta}}(s_t, a_t)].$$

PPO is an *on-policy* algorithm, meaning it learns exclusively from trajectories generated by its current policy. This stabilises training but requires discarding past data once the policy updates. By contrast, off-policy methods such as Q-learning or SAC update from a behaviour policy  $\mu \neq \pi_{\theta}$ , reusing past trajectories to improve sample efficiency.

The key innovation of PPO is its *clipped surrogate loss*, which stabilises learning by preventing excessively large policy updates. With generalised advantage estimation (GAE), the PPO objective is

$$L^{\text{CLIP}}(\theta) = \mathbb{E}_t \left[ \min \left( r_t(\theta) \hat{A}_t, \text{clip} \left( r_t(\theta), 1 - \epsilon, 1 + \epsilon \right) \hat{A}_t \right) \right],$$

where

$$r_t(\theta) = \frac{\pi_{\theta}(a_t | s_t)}{\pi_{\theta_{\text{old}}}(a_t | s_t)}.$$

Here,  $\hat{A}_t$  denotes the estimated advantage of action  $a_t$  at state  $s_t$ , and  $\epsilon$  (typically 0.1-0.3) controls the clipping range. The clipping prevents  $r_t(\theta)$  from deviating too far from 1, thereby limiting the size of policy updates. PPO also incorporates a separate value-function loss and an entropy bonus to balance exploitation and exploration.

In addition to the clipped policy objective, PPO optimises a state-value baseline  $V_{\phi}(s_t)$  using a squared-error loss:

$$L^{\text{VF}}(\phi) = \mathbb{E}_t \left[ (V_{\phi}(s_t) - \hat{R}_t)^2 \right],$$

where  $\hat{R}_t$  is the empirical return or bootstrapped target. This helps reduce variance in policy-gradient updates by ensuring the critic approximates the long-term execution cost of continuing from state  $s_t$ .

To avoid premature convergence to deterministic (and possibly suboptimal) policies, PPO adds an entropy regularisation term:

$$L^{\text{entropy}}(\theta) = \mathbb{E}_t [\mathcal{H}(\pi_{\theta}(\cdot | s_t))],$$

where  $\mathcal{H}$  is the Shannon entropy. This encourages exploration by rewarding policies that maintain uncertainty over possible actions.

Putting it all together, the PPO loss combines the clipped surrogate policy objective with a value-function regression term and an entropy bonus:

$$\begin{aligned} \mathcal{L}_{\text{PPO}}(\theta, \phi) = \mathbb{E}_t \bigg[ & \underbrace{\min \left( r_t(\theta) \hat{A}_t, \text{clip} \left( r_t(\theta), 1 - \epsilon, 1 + \epsilon \right) \hat{A}_t \right)}_{L^{\pi}} \\ & - c_v \underbrace{(V_{\phi}(s_t) - \hat{R}_t)^2}_{L^V} + c_e \underbrace{\mathcal{H}(\pi_{\theta}(\cdot | s_t))}_{L^H} \\ & - c_{\text{KL}} \underbrace{\text{KL} \left( \pi_{\theta_{\text{old}}}(\cdot | s_t) \| \pi_{\theta}(\cdot | s_t) \right)}_{L^{\text{KL}}} \bigg], \end{aligned} \quad (2)$$

We implement PPO agents with two distinct feature extractor architectures. The first is an multilayer perceptron (MLP) extractor, which normalises the flattened observation vector and passes it through two fully connected layers with ReLU activations. This design is lightweight and fast, making it well-suited to compact, tabular state representations. The second applies one-dimensional convolutions across the feature dimension with three blocks (64, 64, 128 channels), SiLU activations, and group normalization, providing additional representational capacity at the cost of increased computation.

**Observation Preprocessing:** Raw observations are normalised using running mean and standard deviation estimates maintained across vectorised environments (Stable-Baselines3 VecNormalize wrapper), ensuring numerical stability across assets and regimes.

Hyperparameters follow standard PPO best practices (Schulman et al., 2017) with minor adjustments for the execution domain.

##### Common PPO Settings

**Architecture:** Shared feature extractor (256-dim); actor MLP [256, 256, 128]; critic MLP [256, 256, 128]; tanh activation.

**Optimiser:** PPO with clipped surrogate loss  $L^\pi$ , value loss  $L^V$ , entropy bonus  $L^H$ , and KL penalty  $L^{KL}$  (Eq. 2).

##### Key Hyperparameters:

- Rollout:  $n_{\text{steps}} = 2048$  per environment, discount  $\gamma = 0.999$
- Batch size: Auto-scaled by rollout size  $\in \{2048, 4096, 8192\}$
- Training: 3 epochs, clip range  $\epsilon \approx 0.18$  (linear decay)
- Regularization: target KL = 0.02, entropy coefficient = 0.006
- Value loss coefficient = 0.55, max gradient norm = 0.5

**Learning Rate:** Linear decay from  $3 \times 10^{-4}$  to 0.

**GAE:**  $\lambda = 0.95$  for advantage estimation.

#### 2.4.2 MAP-Elites: Quality-Diversity Optimisation

Most reinforcement learning algorithms optimise for a single performance objective, aiming to find the policy  $\pi_\theta$  that maximises expected return. While this produces a single “best” solution under the training reward, it provides little insight into the diversity of alternative strategies or their robustness under changing market conditions. The *MAP-Elites* algorithm, introduced by Mouret and Clune (2015), belongs to the class of *quality-diversity* (QD) methods. Rather than converging on a single optimum, MAP-Elites searches for a collection of high-performing yet behaviourally distinct solutions, yielding a repertoire of policies that together “illuminate” the range of possible strategies.

##### MAP-Elites Algorithm (overview)

**Inputs:** behaviour-descriptor mapping  $b(\pi) \in \mathbb{R}^d$ , archive grid  $\mathcal{G}$  partitioning descriptor space, quality function  $Q(\pi)$ , variation operator  $\text{Var}(\cdot)$ .

1. **Initialisation.** Generate candidate policies  $\{\pi^{(i)}\}$ . For each, evaluate  $Q(\pi^{(i)})$  and compute descriptor  $z^{(i)} = b(\pi^{(i)})$ .
2. **Archive update.** Map  $z^{(i)}$  to grid cell  $c$ . If  $\mathcal{G}[c]$  is empty, insert  $\pi^{(i)}$ ; if occupied, replace only if  $Q(\pi^{(i)})$  exceeds the incumbent via the quality function.
3. **Variation.** Sample elites from  $\mathcal{G}$  and generate offspring by perturbing their representation.
4. **Iteration.** Evaluate offspring, compute descriptors, and update  $\mathcal{G}$ . Iterate until evaluation budget is exhausted.

**Output:** repertoire  $\mathcal{G}$  of elites  $\{\pi_c^*\}$ , one per descriptor cell, each maximising  $Q(\pi)$  locally.

The quality function  $Q(\pi)$  is the negative mean total execution cost averaged over evaluation episodes, where lower cost (better execution) yields higher quality. Each policy is evaluated on orders matching its phenotype to ensure fair niche-specific comparison.

When applying variation to neural networks, we perturb the weights  $\theta$  that define the extractors allowing for variability. Offspring are generated by applying Gaussian noise ( $\mathcal{N}(0, \sigma^2)$ ) to parent policy parameters. This preserves learned behaviors while introducing local variation.

Each cell in the archive corresponds to a region of descriptor space. MAP-Elites guarantees that only the best-known policy for each behavioural niche is retained. Over many iterations, the archive becomes populated with a structured set of strategies that are both high quality and diverse.

In our implementation, descriptors are designed to capture the fundamental market dimensions of *liquidity* and *volatility*. Both are normalised by their empirical quantiles across the universe, mapping values to the unit interval  $[0, 1]$  in a rank-preserving way:

![Figure 6: MAP-Elites archive across liquidity and volatility descriptors. The plot shows a 6x6 grid with 'Liquidity' on the x-axis and 'Volatility' on the y-axis. Some cells are filled with green and labeled with a Q-value, representing the highest-quality policy discovered in that region. The legend indicates that green cells are 'Elite' and white cells are 'Empty cell'.](177e8bc1c595b7fe3461d9919f87e044_img.jpg)

| Volatility \ Liquidity | L1     | L2     | L3     | L4     | L5     | L6     |
|------------------------|--------|--------|--------|--------|--------|--------|
| V1                     |        |        |        | Q=0.67 |        |        |
| V2                     |        | Q=0.53 |        |        |        |        |
| V3                     |        |        |        |        | Q=0.70 |        |
| V4                     |        |        | Q=0.61 |        |        |        |
| V5                     | Q=0.58 |        |        |        |        | Q=0.50 |
| V6                     |        |        |        |        |        |        |

Figure 6: MAP-Elites archive across liquidity and volatility descriptors. The plot shows a 6x6 grid with 'Liquidity' on the x-axis and 'Volatility' on the y-axis. Some cells are filled with green and labeled with a Q-value, representing the highest-quality policy discovered in that region. The legend indicates that green cells are 'Elite' and white cells are 'Empty cell'.

Figure 6: MAP-Elites archive across liquidity and volatility descriptors. Each filled cell stores the highest-quality policy (elite) discovered in that region.

- **Liquidity.** Quantile-normalised average daily volume (ADV) of symbol  $S$ :

$$b^{\text{liq}}(S) = \frac{1}{N} \sum_{j=1}^N \mathbf{1}\{\text{ADV}(S_j) \leq \text{ADV}(S)\},$$

where  $N$  is the number of symbols in the universe.

- **Volatility.** Quantile-normalised one-day Parkinson estimator:

$$b^{\text{vol}}(S) = \frac{1}{N} \sum_{j=1}^N \mathbf{1}\{\hat{\sigma}^{(1)}(S_j) \leq \hat{\sigma}^{(1)}(S)\},$$

$$\text{where } \hat{\sigma}^{(1)}(S) = \sqrt{\frac{1}{4 \ln 2} \left[ \ln \left( \frac{P^H}{P^L} \right) \right]^2}.$$

Thus, each policy  $\pi_\theta$  is mapped into the two-dimensional descriptor space

$$b(\pi_\theta) = (b^{\text{liq}}(S), b^{\text{vol}}(S)) \in [0, 1]^2,$$

with archive cells representing liquidity-volatility niches.

MAP-Elites offers potential advantages: it may enforce exploration of behaviourally distinct strategies, produce an interpretable map of “what works where,” provide robustness through diverse repertoires, and remain agnostic to policy representation. In this work, we apply MAP-Elites to a PPO-based CNN policy using liquidity-volatility descriptors to structure the archive. However, as we show in Section 3, the practical benefits depend critically on descriptor choice, fitness function design, and computational budget.

## 3 Results

### 3.1 Transient Impact Model Calibration

We calibrate the propagator model parameters  $(G_0, \tau)$  by regressing returns  $r_t$  onto lagged signed volumes  $\epsilon_{t-\ell} f(v_{t-\ell})$  across multiple lags  $\ell = 1, \dots, L$ . Parameters are chosen to maximise out-of-sample  $R^2$  across rolling windows of one-minute level data for 400+ S&P 500 stocks during 2022 (excluding stocks with insufficient or missing one-minute level data).

Two functional forms for  $f(v)$  were compared: linear and square-root. Consistent with empirical microstructure studies, the square-root form achieved higher mean  $R^2$  across symbols and was adopted as the baseline:

$$f(v_t, q_t) = \gamma \sqrt{\frac{|q_t|}{v_t}},$$

![Figure 7: Box plot titled 'tau statistics - 10 day max window'. The y-axis is labeled 'tau' and ranges from 0 to 200. The x-axis lists various tau statistics: tau, tau_pos, tau_weighted, tau_median_21, tau_median_31, tau_median_42, tau_median_63, tau_pos_median_21, tau_pos_median_31, tau_pos_median_42, tau_pos_median_63, tau_weighted_median_21, tau_weighted_median_31, tau_weighted_median_42, and tau_weighted_median_63. The 'tau' box plot shows a median around 110 and a lower whisker below 0. The 'tau_pos' box plot shows a median around 40 and a lower whisker at 0. The remaining box plots show medians around 10-20 and lower whiskers at 0. Outliers are shown as open circles above the boxes.](b3df5964338063224492c01f09e4fed6_img.jpg)

Figure 7: Box plot titled 'tau statistics - 10 day max window'. The y-axis is labeled 'tau' and ranges from 0 to 200. The x-axis lists various tau statistics: tau, tau\_pos, tau\_weighted, tau\_median\_21, tau\_median\_31, tau\_median\_42, tau\_median\_63, tau\_pos\_median\_21, tau\_pos\_median\_31, tau\_pos\_median\_42, tau\_pos\_median\_63, tau\_weighted\_median\_21, tau\_weighted\_median\_31, tau\_weighted\_median\_42, and tau\_weighted\_median\_63. The 'tau' box plot shows a median around 110 and a lower whisker below 0. The 'tau\_pos' box plot shows a median around 40 and a lower whisker at 0. The remaining box plots show medians around 10-20 and lower whiskers at 0. Outliers are shown as open circles above the boxes.

Figure 7: Constraint necessity: without bounds,  $\tau$  can turn negative due to noise (Eq. 1), implying explosion rather than decay.

where  $q_t$  is the signed traded quantity at time  $t$ , and  $v_t$  is the market volume for the period  $t$  and  $\gamma$  is the impact coefficient.

The decay kernel  $G(\ell)$  captures temporal persistence of impact:

$$G(\ell) = G_0 e^{-\ell/\tau},$$

where  $G_0$  is the immediate impact coefficient,  $\ell$  is the lag since the trade, and  $\tau$  the characteristic decay horizon.

Calibration is performed via constrained non-linear least squares with economically interpretable bounds:

$$G_0 \geq 0, \quad \tau \in [0.5, 180].$$

The necessity of these constraints is demonstrated in Figure 7.

Figure 8 presents a lagged regression study comparing  $R^2$  of linear and square-root forms at maximum lags  $L$  of 5, 10, and 20 minutes. The square-root function dominates overall, especially for liquid names where concavity captures diminishing marginal impact (Figure 9).

After cross-validation, we store the best  $(\ell, \tau, \gamma)$  and average  $\bar{R}^2$  for reuse, retaining only symbols with  $\bar{R}^2 > 0.02$ . This threshold leaves about two-thirds of the universe available for training and testing. Stocks below this threshold are excluded from the training, validation and test sets.

### 3.2 RL Performance Results

#### 3.2.1 Evaluation of RL models

For evaluation, we adopt a strict train-test separation based on non-overlapping calendar periods. The training set consists of orders generated between January 1, 2022 and September 30, 2022, while the evaluation set spans October 1 to December 31, 2022.

Training is performed within the GEO environment, which integrates Gymnasium for vectorised simulation. For each experiment, we generate a large set of synthetic parent orders (5,000-25,000 per run) sampled across the universe described. Orders are balanced between buys and sells and cover a range of sizes and horizons. The exact same training and evaluation orders are shared across all policies to guarantee a fair comparison.

We benchmark PPO with multi-layer perceptron (MLP) and convolutional (CNN) feature extractors, MAP-Elites, and baseline strategies (TWAP, VWAP, POV, and Random). To mitigate the influence of outliers, we exclude pathological orders and winsorise evaluation metrics at the 1st and 99th percentiles before aggregation.

![Figure 8: R^2 Performance Comparison: Linear vs Square Root Epsilon. The figure consists of eight box plots arranged in a 2x4 grid. The top row shows 'Linear' performance and the bottom row shows 'Square Root' performance. The columns represent different lag values: 'Overall R^2 Distribution', 'Max Lag = 5', 'Max Lag = 10', and 'Max Lag = 20'. Each plot shows the distribution of Mean R^2 for a set of stocks. The Square Root model generally shows higher Mean R^2 values than the Linear model, especially at shorter lags and for the overall distribution.](f4d72193f77f6646a2a1f4baaa927154_img.jpg)

Figure 8: R^2 Performance Comparison: Linear vs Square Root Epsilon. The figure consists of eight box plots arranged in a 2x4 grid. The top row shows 'Linear' performance and the bottom row shows 'Square Root' performance. The columns represent different lag values: 'Overall R^2 Distribution', 'Max Lag = 5', 'Max Lag = 10', and 'Max Lag = 20'. Each plot shows the distribution of Mean R^2 for a set of stocks. The Square Root model generally shows higher Mean R^2 values than the Linear model, especially at shorter lags and for the overall distribution.

Figure 8:  $R^2$  comparison of linear vs. square-root instantaneous impact across lags  $\ell = 1, \dots, L$  for  $L \in \{5, 10, 20, 30\}$ . Square-root dominates in liquid names and shorter horizons.

![Figure 9: Aggregate R^2 outcomes: the square-root specification outperforms linear on average, supporting its choice as the baseline model. The figure is a histogram titled 'Distribution of R^2 by epsilon_type_best (per stock)'. The x-axis is 'R^2 (mean_r2)' ranging from 0.00 to 0.35. The y-axis is 'Count of stocks' ranging from 0 to 100. Two distributions are shown: 'sqrt' (blue) and 'linear' (orange). The 'sqrt' distribution is centered around 0.02, while the 'linear' distribution is centered around 0.01. The 'sqrt' distribution has a higher count of stocks in the 0.01 to 0.03 range, indicating better performance on average.](fdcfba1180dc160c7d539c5fb2a6c1e6_img.jpg)

Figure 9: Aggregate R^2 outcomes: the square-root specification outperforms linear on average, supporting its choice as the baseline model. The figure is a histogram titled 'Distribution of R^2 by epsilon\_type\_best (per stock)'. The x-axis is 'R^2 (mean\_r2)' ranging from 0.00 to 0.35. The y-axis is 'Count of stocks' ranging from 0 to 100. Two distributions are shown: 'sqrt' (blue) and 'linear' (orange). The 'sqrt' distribution is centered around 0.02, while the 'linear' distribution is centered around 0.01. The 'sqrt' distribution has a higher count of stocks in the 0.01 to 0.03 range, indicating better performance on average.

Figure 9: Aggregate  $R^2$  outcomes: the square-root specification outperforms linear on average, supporting its choice as the baseline model.

#### 3.2.2 PPO Results and Findings

Table 1 summarises performance for the two PPO architectures compared to baseline strategies. Metrics are expressed in basis points (bps), with standard errors in parentheses.

The PPO-CNN model achieves the lowest arrival slippage of all strategies (2.13 bps), a statistically significant improvement where  $p < 0.05$ , relative to VWAP, TWAP, and POV. PPO-MLP delivers performance comparable to the random baseline on slippage but still far outperforms benchmarks on cost. Both PPO agents reduce total cost dramatically, halving costs relative to TWAP (303 bps) and cutting more than 60% compared to VWAP (476 bps).

| Agent   | Count | Notional (Bn) | Arrival Slippage | Duration % | Return       | Total Cost    | Action %     |
|---------|-------|---------------|------------------|------------|--------------|---------------|--------------|
| ppo_mlp | 4900  | 21.32         | 3.78 (0.93)      | 99.2       | -5.19 (1.41) | 178.26 (1.77) | 18.25 (0.06) |
| vwap    | 4900  | 21.66         | 5.23 (1.01)      | 99.2       | -5.60 (1.43) | 476.11 (6.09) | 12.51 (0.08) |
| random  | 4900  | 21.31         | 3.77 (0.96)      | 99.2       | -3.46 (1.41) | 217.58 (2.23) | -0.02 (0.06) |
| pov     | 4900  | 21.30         | 4.07 (0.97)      | 99.3       | -3.87 (1.41) | 211.71 (2.21) | 0.00 (0.00)  |
| twap    | 4900  | 20.18         | 7.01 (0.90)      | 98.8       | 1.70 (1.40)  | 302.89 (3.25) | 75.59 (0.05) |
| ppo_cnn | 4900  | 21.41         | 2.13 (0.92)      | 99.2       | -5.68 (1.41) | 178.70 (1.78) | 19.00 (0.06) |

Table 1: Execution summary for PPO and baseline strategies. Arrival slippage, Return, and Total Cost in basis points (bps); Standard errors in parentheses; Duration % is the average portion of  $H$  before completion; Action is the mean  $a_t$  over all parents; Return: intra-order price drift;

Table 2: MAP-Elites specialist fitness (total cost) performance by market regime

| Volatility     | Liquidity | Fitness         | vs CNN Policy |
|----------------|-----------|-----------------|---------------|
| Low            | Low       | -0.01672        | -3.3%         |
| Low            | Medium    | -0.01637        | -1.2%         |
| Low            | High      | -0.01574        | +2.7%         |
| Medium         | Low       | -0.01834        | -13.3%        |
| Medium         | Medium    | -0.01487        | +8.1%         |
| Medium         | High      | -0.01467        | +9.3%         |
| High           | Low       | -0.02107        | -30.2%        |
| High           | Medium    | -0.01451        | +10.3%        |
| High           | High      | -0.01689        | -4.4%         |
| <b>Overall</b> |           | <b>-0.01657</b> | <b>-2.4%</b>  |

Both PPO agents adopt a front-loaded pattern consistent with Almgren-Chriss intuition, mitigating holding costs by executing earlier. The CNN variant moderates this front-loading when returns are adverse, suggesting that the temporal structure enables a more nuanced response to price drift (Figures 10 and 11).

### 3.3 MAP-Elites Results and Findings

#### 3.3.1 Exploratory Application of MAP-Elites

We conducted a preliminary investigation of MAP-Elites for generating regime-specialist policies. While quality-diversity approaches have shown promise in robotics (Mouret and Clune, 2015), their application to financial execution remains largely unexplored. We implemented MAP-Elites over volatility (normalised Parkinson) and liquidity (normalised ADV) behavioural descriptors with a  $3 \times 3$  grid, seeding policies from a baseline PPO-CNN model and evolving them via Gaussian parameter perturbations ( $\sigma = 0.01$ ). Initial experiments with modest configurations (30-100 iterations) showed promising in-sample improvements but failed to generalise. We therefore scaled to 500 iterations with 256 children per generation, evaluating 128,000 candidate policies over 5.5 hours on Apple M4 Max 64GB 16-core CPU.

Table 2 presents phenotype-specific performance: each specialist was evaluated exclusively on test orders matching its liquidity-volatility cell. Three cells achieved 8-10% improvements over baseline PPO within their training niches, while others showed degradation, particularly in low-liquidity regimes. These findings suggest potential for quality-diversity methods but indicate that effective deployment requires careful consideration of regime boundaries, training data density per cell, and selective application strategies.

The archive reveals striking heterogeneity in generalisation. Three cells achieved 8-10% improvements over baseline, with the high-volatility/medium-liquidity cell performing best at +10.3%. Conversely, the high-volatility/low-liquidity cell degraded catastrophically (-30.2%), suggesting overfitting in illiquid regimes. While the overall cell average showed -2.4% degradation, individual specialists demonstrate that regime-specific policies can outperform universal approaches when properly matched to market conditions.

These results motivate development of ensemble routing strategies that selectively deploy specialists only in regimes where they demonstrate robust out-of-sample improvements. Such meta-policies are left for future work.

![Figure 10: Four line charts showing aggregated mean action % across normalized horizons for different side-adj return tertiles. The top chart shows overall performance, while the bottom three show positive, neutral, and negative side-adj return tertiles. Each chart compares ppo_mlp_cpu_nsteps_2048_b, ppo_cnn_cpu_nsteps_2048_b, and their respective return and bps components. The x-axis represents normalized horizon from 0.05 to 0.95. The left y-axis shows action percentage (10-22%), and the right y-axis shows side-adj return in bps (ranging from -100 to 100).](7bed2d7c96d86bf922295a1252da52a5_img.jpg)

Figure 10: Four line charts showing aggregated mean action % across normalized horizons for different side-adj return tertiles. The top chart shows overall performance, while the bottom three show positive, neutral, and negative side-adj return tertiles. Each chart compares ppo\_mlp\_cpu\_nsteps\_2048\_b, ppo\_cnn\_cpu\_nsteps\_2048\_b, and their respective return and bps components. The x-axis represents normalized horizon from 0.05 to 0.95. The left y-axis shows action percentage (10-22%), and the right y-axis shows side-adj return in bps (ranging from -100 to 100).

Figure 10: Aggregated mean action  $\% a_t$  across order horizons, conditioned on price drift relative to order side. PPO agents exhibit front-loading consistent with Almgren-Chriss scheduling.

## 4 Discussion

### 4.1 GEO Environment and RL Performance

We introduced GEO, a Gymnasium-compatible environment for optimal execution that integrates calibrated transient impact models with vectorized simulation. GEO’s design enables direct transfer between backtesting and live deployment, reducing the sim-to-real gap inherent in custom execution simulators.

Within GEO, PPO-CNN achieved 2.13 bps arrival slippage, outperforming VWAP (5.23 bps) and TWAP (7.01 bps) by 59% and 70% respectively. Both PPO agents reduced total costs to 178 bps, roughly half TWAP’s 303 bps, primarily through front-loaded schedules that internalize holding costs. Figure 14 shows the “anatomy” of a single PPO-CNN order, illustrating how the propagator affects fill prices, how inventory is managed, and how costs accumulate. This integrated view demonstrates how the RL agent perceives state, chooses actions, and experiences costs under the transient impact model.

The CNN’s advantage over MLP (3.78 bps) despite processing identical 13-dimensional observations demonstrates that architectural improvements yield measurable gains. The convolutional layers enable learning joint patterns between correlated features—price, volume, and inventory states—where the MLP treats each

![Figure 11: Decomposition of costs across strategies. The plot shows cost over time (minutes) for various components: arrival_cost (blue), swap_cost (green), rate_penalty (orange), holding_risk_cost (red), unfilled_cost (purple), total_exp_cost (pink), and Order Completed (dotted line). The holding_risk_cost (red) shows significant spikes, particularly around 150 and 270 minutes, indicating high volatility or risk. The total_exp_cost (pink) is relatively stable, while the arrival_cost (blue) and swap_cost (green) remain low throughout the period.](96a7eac66ef72bb016c280278506ac63_img.jpg)

Figure 11: Decomposition of costs across strategies. The plot shows cost over time (minutes) for various components: arrival\_cost (blue), swap\_cost (green), rate\_penalty (orange), holding\_risk\_cost (red), unfilled\_cost (purple), total\_exp\_cost (pink), and Order Completed (dotted line). The holding\_risk\_cost (red) shows significant spikes, particularly around 150 and 270 minutes, indicating high volatility or risk. The total\_exp\_cost (pink) is relatively stable, while the arrival\_cost (blue) and swap\_cost (green) remain low throughout the period.

Figure 11: Decomposition of costs across strategies. PPO agents internalise holding cost, which drives front-loading behaviour.

independently. Figure 10 shows the CNN moderating front-loading during adverse price drift, suggesting context-dependent adaptation beyond the MLP’s static aggressiveness.

These improvements occur within a simulator calibrating exponential impact decay on one-minute level data with  $R^2 \approx 0.02\text{-}0.10$ . While this explained variance appears modest, it reflects realistic microstructure signal-to-noise ratios. The results represent performance under calibrated impact dynamics, not predictions of live execution.

### 4.2 Quality-Diversity: Current Results and Future Potential

MAP-Elites revealed substantial regime heterogeneity. Three cells achieved 8-10% improvements, with high-volatility/medium-liquidity reaching +10.3%. However, high-volatility/low-liquidity degraded -30.2%, and the overall ensemble averaged -2.4% below baseline.

The pattern is clear: specialists succeed in data-rich regimes with strong signal (medium liquidity provides training orders, high volatility amplifies impact patterns) but catastrophically overfit in sparse cells. Our implementation used simple Gaussian parameter mutations over 500 iterations—a conservative approach that prioritizes interpretability over computational efficiency.

Recent advances suggest substantial room for improvement. Parallelized quality-diversity (Lim et al., 2023) could reduce the 5.5-hour runtime by orders of magnitude. Specialized mutation operators for neural networks (Faldor et al., 2025) may improve exploration efficiency beyond naive Gaussian noise. Methods designed for stochastic objectives (Flageat et al., 2025) could better handle the inherent noisiness of financial data, where fitness evaluation on small order samples introduces high variance.

Effective deployment requires validation-based selection—use only specialists demonstrating robust out-of-sample gains—and intelligent routing that falls back to the baseline in low-confidence regimes. The  $3 \times 3$  grid may be too coarse; finer phenotype partitions or continuous descriptor spaces warrant investigation. With these refinements, quality-diversity methods could provide interpretable performance maps across market regimes while maintaining robustness.

### 4.3 Practical Implications

RL-based execution appears viable for institutional-scale orders where multi-basis-point improvements justify development costs. The CNN architecture provides a strong baseline without requiring complex temporal models or extensive feature engineering. Quality-diversity methods show promise for discovering regime specialists but require substantial compute and careful validation before deployment.

Key limitations remain: our impact model makes stationarity assumptions, calibration quality varies across stocks, and all results derive from simulation. Live validation would address questions of latency, partial fills, and strategic interaction with other market participants. Nevertheless, these results demonstrate that RL execution has progressed from academic curiosity toward practical consideration for well-resourced trading operations.

![Figure 12: 3D surface plots showing MAP-Elites archive evolution over 100 iterations. The left plot shows Training Performance (Base: -0.0108) and the right plot shows Test Performance (Base: -0.0163 | Improvement: -3.0%). Both plots show fitness (negative total cost) as a function of Volatility and Liquidity. A red plane represents the baseline PPO-CNN fitness. The training set shows improvements across all cells, while the test set shows mixed generalization with failures in low-liquidity regimes.](2a77eb32ef4c4d8a5c1758a53a908336_img.jpg)

Figure 12 displays two 3D surface plots illustrating the MAP-Elites archive evolution over 100 iterations. The left plot, titled "Training Performance" (Base: -0.0108), shows the fitness (negative total cost) as a function of Volatility (x-axis, 0.00 to 2.00) and Liquidity (y-axis, 0.00 to 2.00). The right plot, titled "Test Performance" (Base: -0.0163 | Improvement: -3.0%), shows the same fitness function for the test set. Both plots include a red plane representing the baseline PPO-CNN fitness. The training set (left) shows improvements across all cells, while the test set (right) shows mixed generalization with failures in low-liquidity regimes.

Figure 12: 3D surface plots showing MAP-Elites archive evolution over 100 iterations. The left plot shows Training Performance (Base: -0.0108) and the right plot shows Test Performance (Base: -0.0163 | Improvement: -3.0%). Both plots show fitness (negative total cost) as a function of Volatility and Liquidity. A red plane represents the baseline PPO-CNN fitness. The training set shows improvements across all cells, while the test set shows mixed generalization with failures in low-liquidity regimes.

Figure 12: MAP-Elites archive evolution over 100 iterations. Z-axis indicates fitness (negative total cost). Red plane shows baseline PPO-CNN fitness. Training set (left) achieves improvements across all cells, whereas test set (right) shows mixed generalization with failures in low-liquidity regimes.

![Figure 13: 3D surface plots showing MAP-Elites archive evolution over 500 iterations. The left plot shows Training Performance (Base: -0.0164) and the right plot shows Test Performance (Base: -0.0162 | Improvement: -2.4%). Both plots show fitness (negative total cost) as a function of Volatility and Liquidity. A red plane represents the baseline PPO-CNN fitness. The training set shows improvements across all cells, and the test set shows improved results compared to the 100 iteration run.](79cb7fa0e9c78ec5cd0b0de977824f8d_img.jpg)

Figure 13 displays two 3D surface plots illustrating the MAP-Elites archive evolution over 500 iterations. The left plot, titled "Training Performance" (Base: -0.0164), shows the fitness (negative total cost) as a function of Volatility (x-axis, 0.00 to 2.00) and Liquidity (y-axis, 0.00 to 2.00). The right plot, titled "Test Performance" (Base: -0.0162 | Improvement: -2.4%), shows the same fitness function for the test set. Both plots include a red plane representing the baseline PPO-CNN fitness. The training set (left) shows improvements across all cells, while the test set (right) shows improved results vs. the 100 iteration run.

Figure 13: 3D surface plots showing MAP-Elites archive evolution over 500 iterations. The left plot shows Training Performance (Base: -0.0164) and the right plot shows Test Performance (Base: -0.0162 | Improvement: -2.4%). Both plots show fitness (negative total cost) as a function of Volatility and Liquidity. A red plane represents the baseline PPO-CNN fitness. The training set shows improvements across all cells, and the test set shows improved results compared to the 100 iteration run.

Figure 13: MAP-Elites archive evolution. 500 iteration run. Z-axis indicates fitness (negative total cost). Red plane shows baseline PPO-CNN fitness. Training set (left) achieves improvements across all cells, whereas test set (right) shows improved results vs. the 100 iteration run.

![Four stacked plots showing the anatomy of a PPO-CNN RL order execution. The top plot shows Price vs. Time (minutes) with Fill Price, Market VWAP Price, Order VWAP Price, and Order Completed. The second plot shows Quantity vs. Time (minutes) with Shares Remaining and Order Completed. The third plot shows Action % vs. Time (minutes) with Action % and Order Completed. The bottom plot shows Cost vs. Time (minutes) with arrival_cost, vwap_cost, rate_penalty, unfilled_cost, holding_risk_cost, total_step_cost, and Order Completed.](9a19da4f7fccb96a934411c0bb5a386d_img.jpg)

ppo\_cnn\_cpu\_nsteps\_2048\_batchsize\_8192\_epochs\_3 | [AWK | Sell] Order 3 | Total 5,955 Shares | Horizon: 288

The figure displays four vertically stacked plots illustrating the execution of a sell order (Order 3) using a PPO-CNN RL algorithm. The x-axis for all plots is 'Time (minutes)' from 0 to 288.

- Top Plot (Price vs. Time):** The left y-axis is 'Price' (156.5 to 160.0). The right y-axis is 'Total Reward' (0.000 to 0.035). It shows the Fill Price (blue line), Market VWAP Price (green line), Order VWAP Price (purple dashed line), and Order Completed (red dotted line).
- Second Plot (Quantity vs. Time):** The left y-axis is 'Quantity' (0 to 6000). The right y-axis is 'Trade Size' (0 to 140). It shows Shares Remaining (grey dashed line) and Order Completed (red dotted line). Cyan dots represent trade sizes.
- Third Plot (Action % vs. Time):** The left y-axis is 'Action %' (-100 to 100). The right y-axis is 'Accumulated Impact (bps)' (0 to -8). It shows Action % (yellow bars) and Order Completed (red dotted line). A grey dashed line shows the accumulated impact.
- Bottom Plot (Cost vs. Time):** The y-axis is 'Cost' (0.0000 to 0.0005). It shows arrival\_cost (blue line), vwap\_cost (green line), rate\_penalty (orange line), unfilled\_cost (red line), holding\_risk\_cost (purple line), total\_step\_cost (red line), and Order Completed (red dotted line).

Four stacked plots showing the anatomy of a PPO-CNN RL order execution. The top plot shows Price vs. Time (minutes) with Fill Price, Market VWAP Price, Order VWAP Price, and Order Completed. The second plot shows Quantity vs. Time (minutes) with Shares Remaining and Order Completed. The third plot shows Action % vs. Time (minutes) with Action % and Order Completed. The bottom plot shows Cost vs. Time (minutes) with arrival\_cost, vwap\_cost, rate\_penalty, unfilled\_cost, holding\_risk\_cost, total\_step\_cost, and Order Completed.

Figure 14: Anatomy of a PPO-CNN RL order showing propagator-driven fill prices, remaining inventory, policy actions, immediate impact, and cost decomposition.

## A Appendix

### A.1 Data Details

Table 3: Minute bar dataset: Raw and derived data fields by symbol and trading day.

| Field           | Symbol                  | Type    | Description / Formula                                                                                        |
|-----------------|-------------------------|---------|--------------------------------------------------------------------------------------------------------------|
| time            | $t$                     | Raw     | Minute bin within the continuous trading session.                                                            |
| trade_count     | $\nu$                   | Raw     | Number of reported trades in the minute.                                                                     |
| trade_volume    | $V_t$                   | Raw     | Total number of shares traded in the minute.                                                                 |
| hid_vol         | $V_t^{\text{hidden}}$   | Raw     | Reported hidden shares traded in the minute.                                                                 |
| unsided_vol     | $V_t^{\text{unsided}}$  | Raw     | Shares traded with unknown aggressor side.                                                                   |
| sell_vol        | $V_t^{\text{sell}}$     | Raw     | Shares traded on the sell side (aggressive seller).                                                          |
| buy_vol         | $V_t^{\text{buy}}$      | Raw     | Shares traded on the buy side (aggressive buyer).                                                            |
| bid_price       | $p_t^{\text{bid}}$      | Raw     | Best bid quote price at the end of the minute.                                                               |
| ask_price       | $p_t^{\text{ask}}$      | Raw     | Best ask quote price at the end of the minute.                                                               |
| mid_price       | $m_t$                   | Derived | Mid-quote price: $m_t = \frac{p_t^{\text{bid}} + p_t^{\text{ask}}}{2}$ .                                     |
| bid_size        | $\delta_t^{\text{bid}}$ | Raw     | Displayed bid size (shares) at the end of the minute.                                                        |
| ask_size        | $\delta_t^{\text{ask}}$ | Raw     | Displayed ask size (shares) at the end of the minute.                                                        |
| trade_first     | $P_{t, \text{first}}$   | Raw     | First trade price in the minute (removed as predominantly missing).                                          |
| trade_last      | $P_{t, \text{last}}$    | Raw     | Last trade price in the minute.                                                                              |
| trade_high      | $P_{t, \text{high}}$    | Raw     | Highest trade price in the minute.                                                                           |
| trade_low       | $P_{t, \text{low}}$     | Raw     | Lowest trade price in the minute.                                                                            |
| vwap            | $P_{t, \text{vwap}}$    | Raw     | Volume-weighted average trade price in the minute.                                                           |
| trade_imbalance | $\epsilon_t$            | Derived | Signed volume imbalance: $\epsilon_t = \frac{V_t^{\text{buy}} - V_t^{\text{sell}}}{V_t}$ .                   |
| volatility      | $\sigma$                | Derived | Realised volatility from a rolling window (default: 21-min rolling standard deviation of mid-price returns). |

![Figure 15: Summary statistics of cleaned data. The figure contains four subplots: 1. 'NaN % by Column (Cleaned Data)' bar chart showing NaN percentages for various columns like 'nl_vol' (23%), 'vwap' (23%), 'trade_low' (10%), 'trade_high' (10%), and 'trade_last' (0.1%). 2. 'Distribution of NaN % (Cleaned Data)' histogram showing the distribution of NaN percentages across stocks, with a mean of 0.1% and a median of 0.2%. 3. 'Top 15 Stocks NaN % (Cleaned)' bar chart showing the top 15 stocks by NaN percentage, with EPAM at the top (~28%) and LIR at the bottom (~10%). 4. 'NaN % Heatmap (Top 10 Stocks - Cleaned)' heatmap showing NaN percentages for the top 10 stocks across various columns. 5. 'Cleaned Dataset Summary Metrics' bar chart showing the number of stocks for different NaN thresholds: Total Stocks (412), Less than 1% (29), Less than 5% (29), Stocks with >5% NaN (0), and Stocks with >1% NaN (48).](65a9654ccb3d0d452378b0f4c0c392f7_img.jpg)

Figure 15: Summary statistics of cleaned data. The figure contains four subplots: 1. 'NaN % by Column (Cleaned Data)' bar chart showing NaN percentages for various columns like 'nl\_vol' (23%), 'vwap' (23%), 'trade\_low' (10%), 'trade\_high' (10%), and 'trade\_last' (0.1%). 2. 'Distribution of NaN % (Cleaned Data)' histogram showing the distribution of NaN percentages across stocks, with a mean of 0.1% and a median of 0.2%. 3. 'Top 15 Stocks NaN % (Cleaned)' bar chart showing the top 15 stocks by NaN percentage, with EPAM at the top (~28%) and LIR at the bottom (~10%). 4. 'NaN % Heatmap (Top 10 Stocks - Cleaned)' heatmap showing NaN percentages for the top 10 stocks across various columns. 5. 'Cleaned Dataset Summary Metrics' bar chart showing the number of stocks for different NaN thresholds: Total Stocks (412), Less than 1% (29), Less than 5% (29), Stocks with >5% NaN (0), and Stocks with >1% NaN (48).

Figure 15: Summary statistics of cleaned data.

Table 4: Daily dataset fields returned by the aggregation pipeline (stored output).

| Field              | Symbol                 | Description / Formula                                                                                                                                                                                         |
|--------------------|------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| symbol             | $S$                    | Ticker identifier.                                                                                                                                                                                            |
| date               | $d$                    | Trading day (YYYYMMDD).                                                                                                                                                                                       |
| adv_21             | $ADV_{21,d}$           | 21-day rolling average daily volume:<br>$ADV_{21,d} = \frac{1}{21} \sum_{i=0}^{20} V_{d-i}$                                                                                                                   |
| avg_trade_count_21 | $\bar{\nu}_{21,d}$     | 21-day rolling average of daily trade counts:<br>$\bar{\nu}_{21,d} = \frac{1}{21} \sum_{i=0}^{20} \nu_{d-i}$                                                                                                  |
| avg_spread_21      | $\bar{s}_{21,d}$       | 21-day rolling average of the day-level spread metric (units consistent with input <b>spread</b> ).                                                                                                           |
| avg_depth_21       | $\bar{\delta}_{21,d}$  | 21-day rolling average of daily depth, where<br>$\delta_d = \frac{\text{bid\_size}_d + \text{ask\_size}_d}{2}, \quad \bar{\delta}_{21,d} = \frac{1}{21} \sum_{i=0}^{20} \delta_{d-i}$                         |
| vwap               | $P_d^{\text{VWAP}^*}$  | Daily VWAP with fallback: if VWAP is missing, set $P_d^{\text{VWAP}^*} \leftarrow P_d^{\text{last}}$ (last trade price).                                                                                      |
| daily_volatility   | $\hat{\sigma}_d^{(1)}$ | Parkinson volatility (window $w=1$ day), clipped to $[10^{-4}, 2.0]$ :<br>$\hat{\sigma}_d^{(w)} = \sqrt{\frac{1}{4w \ln 2} \sum_{i=0}^{w-1} \left[ \ln \left( \frac{P_{d-i}^H}{P_{d-i}^L} \right) \right]^2}$ |
| daily_vol_lag1     | $\hat{\sigma}_d^{(2)}$ | Parkinson volatility (window $w=2$ days), clipped to $[10^{-4}, 2.0]$ (same formula as above with $w = 2$ ).                                                                                                  |
| daily_vol_5d       | $\hat{\sigma}_d^{(5)}$ | Parkinson volatility (window $w=5$ days), clipped to $[10^{-4}, 2.0]$ (same formula as above with $w = 5$ ).                                                                                                  |
| trade_high         | $P_d^H$                | Highest trade price of day $d$ .                                                                                                                                                                              |
| trade_low          | $P_d^L$                | Lowest trade price of day $d$ .                                                                                                                                                                               |

### A.2 Full list of performance Metrics

Table 5: Evaluation metrics used to assess execution policy performance.

| Metric                                                                  | Mathematical Definition                                                                                                      |
|-------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------|
| Arrival price slippage                                                  | $C_{\text{arrival}} = 10^4 \cdot \text{sided} \left( \frac{\sum_{t=0}^{H-1} P_t^{\text{fill}} q_t}{Q_0} - p_0 \right) / p_0$ |
| Implementation shortfall vs. arrival mid-price $p_0$ , in basis points. |                                                                                                                              |
| <i>Continued on next page</i>                                           |                                                                                                                              |

Table 5 – *continued from previous page*

| Metric                                                                                             | Mathematical Definition                                                                                                         |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------|
| <b>Market VWAP vs. Arrival</b>                                                                     | $C_{\text{mktVWAP}} = 10^4 \cdot \left( \frac{\sum_{t=0}^{H-1} p_t^{\text{mkt}} V_t}{\sum_{t=0}^{H-1} V_t} - p_0 \right) / p_0$ |
| Reference measure of how the market VWAP itself moved relative to arrival, isolating market drift. |                                                                                                                                 |
| <b>VWAP slippage</b>                                                                               | $C_{\text{VWAP}} = \text{sld} \left( \frac{\sum_{t=0}^{H-1} (p_t^{\text{fill}}) q_t}{Q_0} - P^{\text{VWAP}} \right)$            |
| Performance relative to the VWAP benchmark                                                         |                                                                                                                                 |
| <b>Completion rate</b>                                                                             | $\frac{\sum_{t=0}^{H-1} q_t}{Q_0}$                                                                                              |
| Proportion of shares executed by horizon $H$ ; target is 1 (100%).                                 |                                                                                                                                 |
| <b>Horizon usage</b>                                                                               | $\frac{t_{\text{last\_trade}}}{H}$                                                                                              |
| Fraction of horizon consumed before order completion; lower values imply earlier execution.        |                                                                                                                                 |
| <b>Action variability</b>                                                                          | $\text{Var}(a_{0:H-1})$                                                                                                         |
| Variance of policy actions; high variability may indicate unstable strategies.                     |                                                                                                                                 |
| <b>No-trade percentage</b>                                                                         | $\frac{\#\{t : q_t = 0\}}{H}$                                                                                                   |
| Fraction of minutes where no trades were executed; indicates inactivity.                           |                                                                                                                                 |
| <b>High-rate in favourable periods</b>                                                             | $\frac{\#\{t : q_t > p_{\text{target}} V_t \wedge p_t^{\text{stock}} < P_t^{\text{VWAP}}\}}{H}$                                 |
| Share of minutes where the agent accelerated trading when the stock outperformed market VWAP.      |                                                                                                                                 |
| <b>Low-rate in unfavourable periods</b>                                                            | $\frac{\#\{t : q_t < p_{\text{target}} V_t \wedge p_t^{\text{stock}} > P_t^{\text{VWAP}}\}}{H}$                                 |
| Share of minutes where the agent slowed trading when the stock underperformed market VWAP.         |                                                                                                                                 |

## References

- Almgren, R. and Chriss, N. (2001). Optimal execution of portfolio transactions. *The Journal of Risk*, 3(2):5–40.
- Amrouni, S., Moulin, A., Vann, J., Vyetrenko, S., Balch, T., and Veloso, M. (2022). ABIDES-gym: gym environments for multi-agent discrete event simulation and application to financial markets. In *Proceedings of the Second ACM International Conference on AI in Finance, ICAIF '21*, New York, NY, USA. Association for Computing Machinery.
- Bouchaud, J.-P. (2010). Price impact. In *Encyclopedia of Quantitative Finance*. John Wiley & Sons.
- Bouchaud, J.-P., Bonart, J., Donier, J., and Gould, M. (2018). The propagator model. In *Trades, Quotes and Prices: Financial Markets Under the Microscope*, pages 252–253. Cambridge University Press.
- Bucci, F., Benzaquen, M., Lillo, F., and Bouchaud, J.-P. (2019). Crossover from linear to square-root market impact. *Physical Review Letters*, 122:108302.
- Chatzilygeroudis, K., Cully, A., Vassiliades, V., and Mouret, J.-B. (2021). Quality-diversity optimization: A novel branch of stochastic optimization. In Pardalos, P. M., Rasskazova, V., and Vrahatis, M. N., editors, *Black Box Optimization, Machine Learning, and No-Free Lunch Theorems*, pages 109–135. Springer, Cham.
- Cont, R., Kukanov, A., and Stoikov, S. (2014). The price impact of order book events. *Journal of Financial Econometrics*, 12:47–88.
- Faldor, M., Chalumeau, F., Flageat, M., and Cully, A. (2025). Synergizing quality-diversity with descriptor-conditioned reinforcement learning. *ACM Transactions on Evolutionary Learning and Optimization*, 5(1):3 (35 pages).
- Flageat, M., Huber, J., Helenon, F., Doncieux, S., and Cully, A. (2025). Extract-QD framework: A generic approach for quality-diversity in noisy, stochastic or uncertain domains. In *Proceedings of the Genetic and Evolutionary Computation Conference, GECCO '25*, pages 140–148, New York, NY, USA. Association for Computing Machinery.
- Gatheral, J., Schied, A., and Slynko, A. (2012). Transient linear price impact and Fredholm integral equations. *Mathematical Finance*, 22(3):445–474.
- Hafsi, Y. and Vittori, E. (2024). Optimal execution with reinforcement learning. *arXiv preprint arXiv:2411.06389*.
- Hendricks, D. and Wilcox, D. (2014). A reinforcement learning extension to the Almgren-Chriss framework for optimal trade execution. In *2014 IEEE Conference on Computational Intelligence for Financial Engineering & Economics (CIFER)*, pages 457–464.
- Jerome, J., Sánchez-Betancourt, L., Savani, R., and Herdegen, M. (2023). Mbt-gym: Reinforcement learning for model-based limit order book trading. In *Proceedings of the Fourth ACM International Conference on AI in Finance, ICAIF '23*, page 619–627, New York, NY, USA. Association for Computing Machinery.
- Lim, B., Allard, M., Grillotti, L., and Cully, A. (2023). Accelerated quality-diversity through massive parallelism. *Transactions on Machine Learning Research*.
- Mana Tech LLC (2025). Historical u.s. equities market data. <https://manatech.ai/>. Accessed: 2025-08-17.
- Mastromatteo, I., Tóth, B., and Bouchaud, J.-P. (2014). Agent-based models for latent liquidity and concave price impact. *Physical Review Letters*, 113(26):268701.
- Mouret, J.-B. and Clune, J. (2015). Illuminating search spaces by mapping elites. *arXiv preprint arXiv:1504.04909*.
- Nevmyvaka, Y., Feng, Y., and Kearns, M. J. (2006). Reinforcement learning for optimized trade execution. In *Proceedings of the 23rd International Conference on Machine Learning (ICML)*, pages 673–680. ACM.
- Obizhaeva, A. A. and Wang, J. (2013). Optimal trading strategy and supply/demand dynamics. *Journal of Financial Markets*, 16(1):1–32.
- Parkinson, M. (1980). The extreme value method for estimating the variance of the rate of return. *Journal of Business*, 53(1):61–65.
- Perold, A. F. (1988). The implementation shortfall: Paper vs. reality. *The Journal of Portfolio Management*, 14(3):4–9.
- Ray Team (2025). RLLib environments: Farama Gymnasium. <https://docs.ray.io/en/latest/rllib/rllib-env.html>. Accessed: 2026-01-29.

- Schulman, J., Moritz, P., Levine, S., Jordan, M., and Abbeel, P. (2016). High-dimensional continuous control using generalized advantage estimation. In *Proceedings of the International Conference on Learning Representations (ICLR)*.
- Schulman, J., Wolski, F., Dhariwal, P., Radford, A., and Klimov, O. (2017). Proximal policy optimization algorithms. *arXiv preprint arXiv:1707.06347*.
- Stable-Baselines3 Developers (2025). Using custom environments (Gymnasium interface). [https://stable-baselines3.readthedocs.io/en/master/guide/custom\\_env.html](https://stable-baselines3.readthedocs.io/en/master/guide/custom_env.html). Accessed: 2026-01-29.
- Sutton, R. S. and Barto, A. G. (2018). *Reinforcement Learning: An Introduction*. MIT Press, 2nd edition.
- Towers, M., Kwiatkowski, A., Terry, J., Balis, J. U., De Cola, G., Deleu, T., Goulão, M., Kallinteris, A., Krimmel, M., Arjun, K. G., Perez-Vicente, R., Pierré, A., Schulhoff, S., Tai, J. J., Tan, H., and Younis, O. G. (2024). Gymnasium: A standard interface for reinforcement learning environments. *arXiv preprint arXiv:2407.17032*.
- Tóth, B., Lempérière, Y., Deremble, C., de Lataillade, J., Kockelkoren, J., and Bouchaud, J.-P. (2011). Anomalous price impact and the critical nature of liquidity in financial markets. *Physical Review X*, 1(2):021006.