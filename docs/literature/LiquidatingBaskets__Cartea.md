# Trading Co-Integrated Assets with Price Impact✩

## Mathematical Finance, Forthcoming

Alvaro Cartea ´ <sup>a</sup> , Luhui Gan<sup>b</sup> , Sebastian Jaimungal<sup>b</sup>

<sup>a</sup>Department of Mathematics, University of Oxford, Oxford, UK Oxford-Man Institute of Quantitative Finance, Oxford, UK

<sup>b</sup>Department of Statistical Sciences, University of Toronto, Toronto, Canada

## Abstract

Executing a basket of co-integrated assets is an important task facing investors. Here, we show how to do this accounting for the informational advantage gained from assets within and outside the basket, as well as for the permanent price impact of market orders (MOs) from all market participants, and the temporary impact that the agent's MOs have on prices. The execution problem is posed as an optimal stochastic control problem and we demonstrate that, under some mild conditions, the value function admits a closed-form solution, and prove a verification theorem. Furthermore, we use data of five stocks traded in the Nasdaq exchange to estimate the model parameters and use simulations to illustrate the performance of the strategy. As an example, the agent liquidates a portfolio consisting of shares in INTC<sup>1</sup> and SMH<sup>2</sup> . We show that including the information provided by three additional assets (FARO, NTAP, ORCL)<sup>3</sup> considerably improves the strategy's performance; for the portfolio we execute, it outperforms the multi-asset version of Almgren-Chriss by approximately 4 to 4.5 basis points.

Keywords: optimal execution, price impact, co-integration, cross price impact, co-movements, algorithmic trading

<sup>✩</sup>SJ would like to thank NSERC and GRI for partially funding this work.

Email addresses: alvaro.cartea@maths.ox.ac.uk (Alvaro Cartea), ´ luke.gan@mail.utoronto.ca (Luhui Gan), sebastian.jaimungal@utoronto.ca (Sebastian Jaimungal)

<sup>1</sup> INTC: Intel Corporation.

<sup>2</sup>SMH: Market Vectors Semiconductor ETF.

<sup>3</sup>FARO: FARO Technologies. NTAP: NetApp. ORCL: Oracle Corporation.

## 1. Introduction

How to optimally execute a large position in an individual stock has been a topic of intense academic and industry research during the last few years. In contrast, there is scant work on the joint execution of large positions in multiple assets. One of the early papers on optimal execution is by Almgren and Chriss (2001) who consider a discrete-time model where the strategy employs market orders (MOs) only. Extensions of their work, where the agent employs MOs and/or limit orders, include Almgren (2012), Kharroubi and Pham (2010a), Gu´eant et al. (2012), Forsyth et al. (2012), Jaimungal and Kinzebulatov (2013), Guilbaud and Pham (2013), and Cartea and Jaimungal (2015). In the extant literature, if the agent liquidates a portfolio of different assets, these are considered to be correlated, but do not include co-integration, nor do they include the market impact of the order flow from other market participants. This paper fills this gap. We show how an agent executes a basket of assets employing a framework that models the price impact of order flow, and employs the information provided by the co-integration factors that drive the joint dynamics of prices – which may include other assets she is not trading in.

In our framework, the agent's MOs have both temporary and permanent price impact. Temporary impact results from the agent's MOs walking the limit order book (LOB), and permanent impact results from one-sided trading pressure exerted on prices. In contrast to most of the literature (Cartea and Jaimungal (2016c) and Cartea and Jaimungal (2016b) being two notable exceptions), here, MOs of other market participants are treated in the same way as the agent's order: market buy orders exert upward pressure on prices, and market sell orders downward pressure on prices. Furthermore, order flow in one asset may impact the prices of co-integrated assets. This cross-effect is partly caused by trading algorithms that take positions based on the co-movements of assets. Such strategies induce co-movement in order flow and liquidity displayed in the LBOs of the co-integrated assets.

In our setup, permanent impact of order flow is linear in the speeds of trading of all market participants (including the agent), and temporary impact is also linear in the agent's speed of trading. We focus on the execution problem where the agent liquidates shares in m assets and employs information from a collection of n ≥ m co-integrated assets. The agent maximizes terminal wealth and penalizes deviations from an inventory-target schedule. This scenario appears in many applications in practice. For example, agency traders are often faced with liquidating a basket of Eurodollar<sup>4</sup> futures of consecutive maturities. These contracts are highly co-integrated, and not simply correlated, see the discussion in Almgren (2014).

Our setup is related to that of Gˆarleanu and Pedersen (2013) in which the authors optimize

<sup>4</sup>Recall that Eurodollar futures are futures contracts on time deposits denominated in USD, but held in a non-US country.

the discounted, and penalized, future expected excess returns in a discrete-time, infinite-time horizon problem. In their model, prices contain an unpredictable martingale component, and an independent stationary predictable component. The penalty is imposed to account for a version of temporary price impact similar to walking the LOB, and they include a permanent price impact which reverts to zero if there are no trades. Passerini and Vazquez (2016) numerically study a continuous-time, finite horizon, version of Gˆarleanu and Pedersen (2013), and account for crossing the spread or posting limit orders. Our approach differs in five main aspects: (i) our setup is in continuous-time, (ii) the execution horizon is finite, (iii) the agent solves an execution problem where prices are co-integrated (rather than having independent predictable components), (iv) the agent's MOs have permanent and temporary impact, and (v) the MOs of other market participants also have permanent price impact. Moreover, we provide analytic characterizations of the solution to the execution problem.

To illustrate the performance of the strategy we calibrate model parameters to five stocks (INTC, SMH, FARO, NTAP, and ORCL) traded in the Nasdaq exchange and run simulations for variations of the strategy including different levels of urgency and inventory-target schedules, including/excluding a speculative component which allows repurchases of shares. As benchmark we use the multi-asset version of the Almgren-Chriss (AC) strategy where the agent models the correlation between the assets in the basket, but does not model cointegration or employ additional information from other assets. The agent liquidates a basket consisting of 4,600 shares of INTC and 900 shares of SMH which corresponds to 1% and 4% of traded volume over the one hour in which execution occurs.

Additional information from other co-integrated stocks considerably boosts the performance of the strategy. For example, if the level of urgency required by the agent to liquidate the portfolio is high (resp. low) the strategy outperforms AC by 4 (resp. 4.5) basis points. This improvement over AC is due to the quality of the information provided by the cointegrated assets, and due to a speculative component of the strategy which allows the agent to repurchase shares during the liquidation horizon to take advantage of price signals. If the agent is not allowed to speculate, i.e. cannot repurchase shares, the relative savings compared to AC, depending on the level of urgency, are between 2.5 to 3.5 basis points.

Finally, we also illustrate how the strategy performs when the agent has access to only one trading day of data, thus parameter estimates are incorrect. We show that the performance of the strategy is broadly the same as that resulting from that when the agent has enough data to obtain correct parameter estimates.

Our model is also related to the literature on pairs trading in that the agent's strategy benefits from co-integration in asset prices. For example, Mudchanatongsuk et al. (2008) model the log-relationship between a pair of stock prices as an Ornstein-Uhlenbeck process and use this to formulate a trading strategy. More recently, Leung and Li (2015) study the optimal timing strategies for trading a mean-reverting price spread, see also Lei and Xu (2015), and Ngo and Pham (2016). Finally, the work of Tourin and Yan (2013) develops an optimal portfolio strategy for a pair of co-integrated assets. This is generalized to multiple co-integrated assets in Cartea and Jaimungal (2016a), and Lintilhac and Tourin (2016).

The remainder of this paper is structured as follows. Section 2 presents the model for the co-integrated prices and poses the liquidation problem solved by the agent. Section 3 presents the dynamic programming equation and shows the optimal liquidation speeds. Section 4 discusses the Nasdaq exchange data employed to estimate the co-integrating factor of prices, and illustrates the performance of the strategy under different assumptions. Section 5 concludes and proofs are collected in the Appendix.

## 2. Model

The investor must liquidate a portfolio of assets and has a time limit to complete the execution. One simple strategy is to view each stock in the portfolio independently and employ a liquidation algorithm designed for an individual stock, see e.g. Almgren and Chriss (2001), Bayraktar and Ludkovski (2014), Cartea et al. (2015). Treating each stock independently is optimal if the assets in the portfolio do not exhibit any co-movements or dependence.

Here we focus on the general case where a collection of traded assets co-move. Modelling the joint dynamics provides the investor with better information to undertake the liquidation strategy. Ideally, the information employed in the execution strategy is not limited to the constituents of the portfolio to be liquidated, it includes other assets that improve the quality of the information employed in the algorithm. See for example, Cartea et al. (2016) who show how to learn from a collection of assets to trade in a subset of the assets.

The portfolio consists of m assets which are a subset of the n-dimensional vector P = (P <sup>t</sup>)0≤t≤<sup>T</sup> of midprices that the investor employs in the trading algorithm. The midprices are determined by a co-integration factor and the impact of the order flow from all market participants including the investor's orders. Specifically we assume that the midprices satisfy the multivariate stochastic differential equation (SDE)

$$d\mathbf{P}_t = d\mathbf{S}_t + \mathbf{g}(\mathbf{o}_t) dt, \qquad (1)$$

where S denotes the co-integration component of midprices and satisfies

$$d\mathbf{S}_t = \kappa \left( \boldsymbol{\theta} - \mathbf{S}_t \right) dt + \boldsymbol{\sigma}^{\mathsf{T}} d\mathbf{W}_t. \tag{2}$$

Here κ is a n×n matrix, θ is an n-dimensional vector, and σ | is the Cholesky decomposition of the asset prices' correlation matrix Σ (i.e. Σ = σ <sup>|</sup>σ), where the operation <sup>|</sup> denotes the transpose operator. As usual we work on the filtered probability space (Ω, F, P, F = (Ft)0≤t≤<sup>T</sup> ), and W = (Wt)0≤t≤<sup>T</sup> is an n-dimensional Brownian motion with natural filtration Ft .

Moreover g(ot) represents the effect of order flow o = (ot)0≤t≤<sup>T</sup> , with o<sup>t</sup> ∈ R n , from all market participants (including the investor's trades) on midprices, and g : R <sup>n</sup> → R n is a permanent price impact function. Below we give a more detailed account of the effect of order flow on the midprice dynamics – for more details see Cartea and Jaimungal (2016c) who discuss the effect of market order flow on asset prices.

The investor wishes to liquidate the portfolio of m assets over a time window [0, T] – the setup for the acquisition problem is similar, so we do not discuss it here. Her initial inventory in each asset is given by the vector Q<sup>0</sup> ∈ R <sup>m</sup> and she must choose the speed at which she liquidates each one of the assets using MOs only.

We denote by ν = (νt)0≤t≤<sup>T</sup> the vector of liquidation speeds, and by Q<sup>ν</sup> = (Q<sup>ν</sup> t )0≤t≤<sup>T</sup> the vector of (controlled) inventory holding in each asset. The inventory is affected by how fast she trades and satisfies

$$d\mathbf{Q}_t^{\nu} = -\nu_t \, dt \,. \tag{3}$$

In our model all MOs have price impact. We assume that price impact is linear in the speed of trading (see Cartea and Jaimungal (2016c) for extensive data analysis illustrating this fact) and treat the order flow of the investor and other market participants symmetrically. In particular, we denote other agents' aggregated net trading speed by µ = (µ<sup>t</sup> )0≤t≤<sup>T</sup> , which we assume is Markov<sup>5</sup> with infinitesimal generator L <sup>µ</sup>, and assume that is independent<sup>6</sup> of the Brownian motion W. Thus, the price impact of order flow is:

$$g(o_t) = -b \, \mathcal{X}^{\mathsf{T}} \, \boldsymbol{\nu}_t + \overline{b} \, \boldsymbol{\mu}_t \,, \tag{4}$$

where b is the permanent impact n × n symmetric matrix and b is the permanent impact n × n matrix from other agents trading activity. X is a m × n matrix with X ij = 1{i=j} and maps the first m elements of an n-dimensional vector to an m-dimensional vector. Although permanent impact from order flow is treated symmetrically, here we separate the agent's impact from that of other participants should we want to focus on either one when analyzing the strategy.

Therefore, after inserting (4) in (1), the midprice can be expressed as

$$\boldsymbol{P}_{t}^{\nu} = \boldsymbol{S}_{t} + \boldsymbol{b} \, \boldsymbol{\mathcal{X}}^{\mathsf{T}} \left( \boldsymbol{Q}_{t}^{\nu} - \boldsymbol{Q}_{0} \right) + \overline{\boldsymbol{b}} \, \boldsymbol{\mathcal{M}}_{t} \,, \tag{5}$$

<sup>5</sup>We can easily include other factors that drive order flow, as long as the joint process, consisting of the driving factors and order flow itself, is Markov.

<sup>6</sup>This independence assumption can also be relaxed.

where  $\mathcal{M}_t = \int_0^t \boldsymbol{\mu}_u du$  and we use the notation  $\boldsymbol{P}^{\boldsymbol{\nu}}$  to stress that midprices are affected by the investors (controlled) speed of trading.

Our model for price dynamics is related to that used in optimal 'pairs trading' where a speculative strategy is designed to profit from the movement of a collection of co-integrated assets, see Tourin and Yan (2013), Leung and Li (2015), and Cartea and Jaimungal (2016a). Our work is different in that the agent's objective is to execute a basket of co-integrated assets, and more importantly, order flow from all market participants, including the agent's own trades, is explicitly modelled in the price dynamics, and (as discussed below, we account for temporary price impact).

In addition to permanent price impact, the investor receives worse than quoted midprices because her MOs walk the LOBs. This price impact is temporary and only affects the prices the investor receives when selling shares. The execution prices are given by

$$\tilde{\boldsymbol{P}}_{t}^{\nu} = \boldsymbol{\mathcal{X}} \, \boldsymbol{P}_{t}^{\nu} - \boldsymbol{a} \, \boldsymbol{\nu}_{t} \,. \tag{6}$$

 $\boldsymbol{a}$  is an  $m \times m$  positive definite matrix, so the temporary impact is linear in the speed of trading. Without loss of generality, we assume that the first m coordinates of  $\boldsymbol{P}_t^{\boldsymbol{\nu}}$  correspond to the assets the investor trades.

In this setup, the LOBs recover immediately after the execution of the MOs – see Almgren (2003), Alfonsi et al. (2010), Kharroubi and Pham (2010b), Gatheral et al. (2012), Schied (2013), Guéant and Lehalle (2015) for further discussions and generalizations.

Finally, the investor's cash from liquidating shares in the m assets is denoted by  $X^{\nu} = (X^{\nu})_{0 \le t \le T}$  and satisfies the SDE

$$dX_t^{\nu} = (\mathcal{X} P_t^{\nu} - a \nu_t)^{\mathsf{T}} \nu_t dt.$$
 (7)

#### 2.1. Performance criteria and value function

The investor aims at liquidating the portfolio by the terminal date T and maximizes expected terminal wealth while penalizing deviations from a deterministic target inventory  $\mathbf{Q}_t : \mathbb{R}_+ \to \mathbb{R}^m$  satisfying  $\mathbf{Q}_0 = \mathbf{Q}_0$  and  $\mathbf{Q}_T = \mathbf{0}$ .

Her performance criteria is

$$H^{\nu}(t, x, \boldsymbol{p}, \boldsymbol{q}, \boldsymbol{\mu}) = \mathbb{E}_{t, x, \boldsymbol{p}, \boldsymbol{q}, \boldsymbol{\mu}} \left[ X_{T}^{\nu} + (\boldsymbol{P}_{T}^{\nu})^{\mathsf{T}} \boldsymbol{\mathcal{X}}^{\mathsf{T}} \boldsymbol{Q}_{T}^{\nu} - (\boldsymbol{Q}_{T}^{\nu})^{\mathsf{T}} \boldsymbol{\alpha} \boldsymbol{Q}_{T}^{\nu} - (\boldsymbol{Q}_{T}^{\nu})^{\mathsf{T}} \boldsymbol{\alpha} \boldsymbol{Q}_{T}^{\nu} \right] - \phi \int_{t}^{T} (\boldsymbol{Q}_{u}^{\nu} - \boldsymbol{Q}_{u})^{\mathsf{T}} \tilde{\boldsymbol{\Sigma}} (\boldsymbol{Q}_{u}^{\nu} - \boldsymbol{Q}_{u}) du ,$$

$$(8)$$

where the expectation operator  $\mathbb{E}_{t,x,\boldsymbol{p},\boldsymbol{q},\boldsymbol{\mu}}[\cdot]$  represents expectation conditioned on (with a slight abuse of notation)  $X_t^{\boldsymbol{\nu}} = x$ ,  $\boldsymbol{P}_t^{\boldsymbol{\nu}} = \boldsymbol{p}$ ,  $\boldsymbol{Q}_t^{\boldsymbol{\nu}} = \boldsymbol{q}$ , and  $\boldsymbol{\mu}_t = \boldsymbol{\mu}$ , and  $\tilde{\boldsymbol{\Sigma}}$  is an  $m \times m$ 

sub-matrix of the correlation matrix Σ corresponding to the m assets that are being traded. Her value function is

$$H(t, x, \boldsymbol{p}, \boldsymbol{q}, \boldsymbol{\mu}) = \sup_{\boldsymbol{\nu} \in \mathcal{A}} H^{\boldsymbol{\nu}}(t, x, \boldsymbol{p}, \boldsymbol{q}, \boldsymbol{\mu}), \qquad (9)$$

where A is the set of admissible strategies consisting of F-predictable processes such that R T 0 |ν i u | du < +∞, P−a.s., for each asset i the investor is liquidating. The liquidation speeds are not restricted to remain positive – we return to this point in Section 4 when we analyze the empirical performance of the trading strategy.

The first term on the right-hand side of the performance criteria (8) is the terminal cash. The second term represents the cash obtained from liquidating all remaining shares at the end of the trading window at the price P . The third term is the market impact costs from liquidating final inventory which are encoded in the positive definite matrix α > 0.

Furthermore, the term in the second line of (8) represents a running inventory-target penalty where φ ≥ 0 is a penalty parameter. This inventory penalty does not affect the investor's revenues, but affects the optimal liquidation rates. When the value of the inventory penalty parameter φ is high, the strategy is forced to track closely the target Q<sup>t</sup> . This is similar in spirit to Cartea and Jaimungal (2016b) who develop a trading strategy to target VWAP, i.e. volume weighted average price, and similar to Bank et al. (2015) who study how to target general positions (without any price dynamics).

For example, when Q<sup>t</sup> = 0 over the execution window, φ may be interpreted as an urgency parameter. High values of φ correspond to the trader wishing to rid herself of more inventory early on. This particular target is justified in a setting where the investor considers model uncertainty – i.e. she is ambiguity averse. Cartea et al. (2013) show that including a running penalty that curbs the strategy to draw down inventory holdings to zero is equivalent to the agent considering alternative models with stochastic drifts. In that setting, the higher the value of φ, the less confident is the agent about the trend of the midprice, so the quicker the strategy executes the shares.

## 3. Optimal Portfolio Liquidation

In this section we derive the optimal liquidation rates. Our first step is to rewrite the control problem using the fundamental price S as a state variable. Using (7) and integration by parts, the investor's wealth X<sup>ν</sup> T can be written as

$$X_{T}^{\nu} = \int_{0}^{T} (\mathcal{X} \mathbf{S}_{t} - \boldsymbol{a} \boldsymbol{\nu}_{t})^{\mathsf{T}} \boldsymbol{\nu}_{t} dt - \frac{1}{2} (\boldsymbol{Q}_{T}^{\nu} - \boldsymbol{Q}_{0})^{\mathsf{T}} \mathcal{X} \boldsymbol{b} \mathcal{X}^{\mathsf{T}} (\boldsymbol{Q}_{T}^{\nu} - \boldsymbol{Q}_{0})$$
$$- \mathcal{M}_{T}^{\mathsf{T}} \overline{\boldsymbol{b}}^{\mathsf{T}} \mathcal{X}^{\mathsf{T}} \boldsymbol{Q}_{T}^{\nu} + \int_{0}^{T} \boldsymbol{\mu}_{t}^{\mathsf{T}} \overline{\boldsymbol{b}}^{\mathsf{T}} \mathcal{X}^{\mathsf{T}} \boldsymbol{Q}_{t}^{\nu} dt.$$
(10)

From (5), we have

$$(\boldsymbol{P}_{T}^{\nu})^{\mathsf{T}} \boldsymbol{\mathcal{X}}^{\mathsf{T}} \boldsymbol{Q}_{T}^{\nu} = \boldsymbol{S}_{T}^{\mathsf{T}} \boldsymbol{\mathcal{X}}^{\mathsf{T}} \boldsymbol{Q}_{T}^{\nu} + (\boldsymbol{Q}_{T}^{\nu} - \boldsymbol{Q}_{0})^{\mathsf{T}} \boldsymbol{\mathcal{X}} \boldsymbol{b} \boldsymbol{\mathcal{X}}^{\mathsf{T}} \boldsymbol{Q}_{T}^{\nu} + \boldsymbol{\mathcal{M}}_{T}^{\mathsf{T}} \overline{\boldsymbol{b}}^{\mathsf{T}} \boldsymbol{\mathcal{X}}^{\mathsf{T}} \boldsymbol{Q}_{T}^{\nu}, \tag{11}$$

and using (10) and (11), the performance criteria can be written as

$$H^{\nu}(t, x, \boldsymbol{s}, \boldsymbol{q}, \boldsymbol{\mu}) = \mathbb{E}_{t, x, \boldsymbol{s}, \boldsymbol{q}, \boldsymbol{\mu}} \left[ \int_{0}^{T} (\boldsymbol{\mathcal{X}} \boldsymbol{S}_{t} - \boldsymbol{a} \boldsymbol{\nu}_{t})^{\mathsf{T}} \boldsymbol{\nu}_{t} dt + \boldsymbol{S}_{T}^{\mathsf{T}} \boldsymbol{\mathcal{X}}^{\mathsf{T}} \boldsymbol{Q}_{T}^{\nu} + \int_{0}^{T} \boldsymbol{\mu}_{t}^{\mathsf{T}} \overline{\boldsymbol{b}}^{\mathsf{T}} \boldsymbol{\mathcal{X}}^{\mathsf{T}} \boldsymbol{Q}_{t}^{\nu} dt \right.$$

$$+ (\boldsymbol{Q}_{T}^{\nu})^{\mathsf{T}} \left( \frac{1}{2} \boldsymbol{\mathcal{X}} \boldsymbol{b} \boldsymbol{\mathcal{X}}^{\mathsf{T}} - \boldsymbol{\alpha} \right) \boldsymbol{Q}_{T}^{\nu} - \frac{1}{2} (\boldsymbol{Q}_{0})^{\mathsf{T}} \boldsymbol{\mathcal{X}} \boldsymbol{b} \boldsymbol{\mathcal{X}}^{\mathsf{T}} \boldsymbol{Q}_{0}$$

$$- \phi \int_{t}^{T} (\boldsymbol{Q}_{u}^{\nu} - \boldsymbol{Q}_{u})^{\mathsf{T}} \tilde{\boldsymbol{\Sigma}} (\boldsymbol{Q}_{u}^{\nu} - \boldsymbol{Q}_{u}) du \right].$$

$$(12)$$

We further simplify the problem by introducing the transformed processes  $Y^{\nu} = \{Y_t^{\nu}\}_{t\geq 0}$  and  $\mathbf{Z} = \{\mathbf{Z}_t\}_{t\geq 0}$  through the following equalities:

$$Y_t^{\nu} = \int_0^t (\mathcal{X} \mathbf{S}_u - \mathbf{a} \nu_u)^{\mathsf{T}} \nu_u \, du + \boldsymbol{\theta}^{\mathsf{T}} \, \mathcal{X}^{\mathsf{T}} (\boldsymbol{Q}_t^{\nu} - \boldsymbol{Q}_0) + \int_0^t \boldsymbol{\mu}_u^{\mathsf{T}} \, \overline{\boldsymbol{b}}^{\mathsf{T}} \, \mathcal{X}^{\mathsf{T}} \, \boldsymbol{Q}_u^{\nu} \, du, \tag{13}$$

$$Z_t = S_t - \theta \,, \tag{14}$$

in which case  $\boldsymbol{Z}$  and  $Y^{\boldsymbol{\nu}}$  satisfy the SDEs

$$d\mathbf{Z}_t = -\kappa \mathbf{Z}_t dt + \boldsymbol{\sigma}^{\mathsf{T}} d\mathbf{W}_t, \qquad (15)$$

$$dY_t^{\nu} = \left\{ (\mathcal{X} \mathbf{Z}_t - \boldsymbol{a} \nu_t)^{\mathsf{T}} \boldsymbol{\nu}_t + \boldsymbol{\mu}_t^{\mathsf{T}} \overline{\boldsymbol{b}}^{\mathsf{T}} \mathcal{X}^{\mathsf{T}} \boldsymbol{Q}_t^{\nu} \right\} dt, \qquad (16)$$

and the control problem, in the new variables, becomes

$$H(t, y, \boldsymbol{z}, \boldsymbol{q}, \boldsymbol{\mu})$$

$$= \sup_{\boldsymbol{\nu} \in \mathcal{U}} \mathbb{E}_{t,y,\boldsymbol{z},\boldsymbol{q},\boldsymbol{\mu}} \left[ Y_T^{\boldsymbol{\nu}} + \boldsymbol{Z}_T^{\mathsf{T}} \boldsymbol{\mathcal{X}}^{\mathsf{T}} \boldsymbol{Q}_T^{\boldsymbol{\nu}} + \boldsymbol{\theta}^{\mathsf{T}} \boldsymbol{\mathcal{X}}^{\mathsf{T}} \boldsymbol{Q}_0 + (\boldsymbol{Q}_T^{\boldsymbol{\nu}})^{\mathsf{T}} \left( \frac{1}{2} \boldsymbol{\mathcal{X}} \boldsymbol{b} \boldsymbol{\mathcal{X}}^{\mathsf{T}} - \boldsymbol{\alpha} \right) \boldsymbol{Q}_T^{\boldsymbol{\nu}} \right. \\ \left. - \frac{1}{2} (\boldsymbol{Q}_0)^{\mathsf{T}} \boldsymbol{\mathcal{X}} \boldsymbol{b} \boldsymbol{\mathcal{X}}^{\mathsf{T}} \boldsymbol{Q}_0 - \phi \int_t^T (\boldsymbol{Q}_u^{\boldsymbol{\nu}} - \boldsymbol{Q}_u)^{\mathsf{T}} \tilde{\boldsymbol{\Sigma}} \left( \boldsymbol{Q}_u^{\boldsymbol{\nu}} - \boldsymbol{Q}_u \right) du \right],$$

$$(17)$$

where  $\mathcal{U}$  is the set of admissible strategies in the new variables.

#### 3.1. The dynamic programming equation

The dynamic programming principle suggests that the value function (17) is the unique classical solution to the DPE

$$\partial_t H + \mathcal{L}^{\mu} H + \sup_{\nu} \left\{ \mathcal{L}^{\nu} H \right\} - \phi \left( \boldsymbol{q} - \boldsymbol{Q}_t \right)^{\intercal} \tilde{\boldsymbol{\Sigma}} \left( \boldsymbol{q} - \boldsymbol{Q}_t \right) = 0,$$
 (18)

subject to the terminal condition

$$H(T, y, \boldsymbol{z}, \boldsymbol{q}, \boldsymbol{\mu}) = y + \boldsymbol{z}^{\mathsf{T}} \boldsymbol{\mathcal{X}}^{\mathsf{T}} \boldsymbol{q} + \boldsymbol{q}^{\mathsf{T}} \left(\frac{1}{2} \boldsymbol{\mathcal{X}} \boldsymbol{b} \boldsymbol{\mathcal{X}}^{\mathsf{T}} - \boldsymbol{\alpha}\right) \boldsymbol{q} + \boldsymbol{\theta}^{\mathsf{T}} \boldsymbol{\mathcal{X}}^{\mathsf{T}} \boldsymbol{Q}_{0} - \frac{1}{2} \boldsymbol{Q}_{0}^{\mathsf{T}} \boldsymbol{\mathcal{X}} \boldsymbol{b} \boldsymbol{\mathcal{X}}^{\mathsf{T}} \boldsymbol{Q}_{0}, \quad (19)$$

and where  $\mathcal{L}^{\nu}$  is the infinitesimal generator of the process  $(Y^{\nu}, \mathbf{Q}^{\nu}, \mathbf{Z})$ , which acts on a smooth function  $\varphi$  as follows:

$$\mathcal{L}^{\nu}\varphi(t,y,\boldsymbol{z},\boldsymbol{q},\boldsymbol{\mu}) = \left\{ (\boldsymbol{\mathcal{X}}\,\boldsymbol{z} - \boldsymbol{a}\,\boldsymbol{\nu})^{\mathsf{T}}\,\boldsymbol{\nu} + \boldsymbol{\mu}^{\mathsf{T}}\,\overline{\boldsymbol{b}}^{\mathsf{T}}\,\boldsymbol{\mathcal{X}}^{\mathsf{T}}\,\boldsymbol{q} \right\} \partial_{y}\varphi - \boldsymbol{\nu}^{\mathsf{T}}\,\partial_{q}\,\varphi - \boldsymbol{z}^{\mathsf{T}}\,\boldsymbol{\kappa}\,\partial_{z}\,\varphi + \frac{1}{2}\operatorname{Tr}\left(\boldsymbol{\Sigma}\,\partial_{zz}\,\varphi\right) .$$
(20)

Proposition 1. Solving the DPE. The DPE (18) admits the solution

$$H(t,y,\boldsymbol{z},\boldsymbol{q},\boldsymbol{\mu}) = y + \boldsymbol{z}^{\intercal} \boldsymbol{A}(t) \boldsymbol{z} + \boldsymbol{z}^{\intercal} \boldsymbol{B}(t,\boldsymbol{\mu}) + \boldsymbol{q}^{\intercal} \boldsymbol{C}(t) \boldsymbol{q} + \boldsymbol{q}^{\intercal} \boldsymbol{D}(t,\boldsymbol{\mu}) + \boldsymbol{z}^{\intercal} \boldsymbol{E}(t) \boldsymbol{q} + F(t,\boldsymbol{\mu}), \quad (21)$$

if there exists unique matrix-valued functions  $\mathbf{A}(t)$   $(n \times n)$ ,  $\mathbf{B}(t, \boldsymbol{\mu})$   $(n \times 1)$ ,  $\mathbf{C}(t)$   $(m \times m)$ ,  $\mathbf{D}(t, \boldsymbol{\mu})$   $(m \times 1)$ ,  $\mathbf{E}(t)$   $(n \times m)$ , and function  $F(t, \boldsymbol{\mu})$  that satisfy:

(a) The matrix Riccati equation:

$$\dot{G} + G M_1 G + G M_2 + M_2^{\mathsf{T}} G + M_3 = 0,$$
 (22)

with terminal condition  $G(T) = \begin{bmatrix} \mathbf{0}^{(n,n)} & \mathbf{0}^{(n,m)} \\ \mathbf{0}^{(m,n)} & \frac{1}{2} \boldsymbol{\chi} \boldsymbol{b} \boldsymbol{\chi}^{\mathsf{T}} - \boldsymbol{\alpha} \end{bmatrix}$ , where  $G = \begin{bmatrix} 2\boldsymbol{A} & \boldsymbol{E} - \boldsymbol{\mathcal{X}}^{\mathsf{T}} \\ \boldsymbol{E}^{\mathsf{T}} - \boldsymbol{\mathcal{X}} & 2\boldsymbol{C} \end{bmatrix}$ ,  $\mathbf{0}^{(j,k)}$  is a  $j \times k$  matrix of zeros,

$$\boldsymbol{M}_{1} = \frac{1}{2} \begin{bmatrix} \boldsymbol{0}^{(n,n)} & \boldsymbol{0}^{(m,m)} \\ \boldsymbol{0}^{(m,m)} & \boldsymbol{a}^{-1} \end{bmatrix}, \quad \boldsymbol{M}_{2} = \begin{bmatrix} -\kappa & \boldsymbol{0}^{(n,m)} \\ \boldsymbol{0}^{(m,n)} & \boldsymbol{0}^{(m,m)} \end{bmatrix}, \quad and \quad \boldsymbol{M}_{3} = \begin{bmatrix} \boldsymbol{0}^{(n,n)} & -\kappa \boldsymbol{\mathcal{X}}^{\mathsf{T}} \\ -\boldsymbol{\mathcal{X}} \kappa^{\mathsf{T}} & -2\phi \tilde{\boldsymbol{\Sigma}} \end{bmatrix}. \quad (23)$$

(b) The linear matrix PDEs:

$$\dot{\boldsymbol{B}} + \mathcal{L}^{\mu} \boldsymbol{B} - \kappa \, \boldsymbol{B} + \frac{1}{2} \left( \boldsymbol{E}^{\mathsf{T}} - \boldsymbol{\mathcal{X}} \right)^{\mathsf{T}} \boldsymbol{a}^{-1} \, \boldsymbol{D} = \boldsymbol{0}^{(n)} \,, \tag{24a}$$

$$\dot{\boldsymbol{D}} + \mathcal{L}^{\mu} \boldsymbol{D} + \boldsymbol{C}^{\dagger} \boldsymbol{a}^{-1} \boldsymbol{D} + 2 \phi \tilde{\boldsymbol{\Sigma}} \boldsymbol{Q}_{t} + \boldsymbol{\mathcal{X}} \overline{\boldsymbol{b}} \boldsymbol{\mu} = \boldsymbol{0}^{(m)}, \tag{24b}$$

$$\dot{F} + \mathcal{L}^{\mu}F + \frac{1}{4}\mathbf{D}^{\dagger}\mathbf{a}^{-1}\mathbf{D} + Tr(\mathbf{\Sigma}\mathbf{A}) - \phi \,\mathbf{Q}_{t}^{\dagger}\,\tilde{\mathbf{\Sigma}}\,\mathbf{Q}_{t} = 0,$$
(24c)

with terminal conditions

$$\boldsymbol{B}(T,\cdot) = \mathbf{0}^{(n)}, \quad \boldsymbol{D}(T,\cdot) = \mathbf{0}^{(m)}, \quad F(T) = \boldsymbol{\theta}^{\mathsf{T}} \boldsymbol{\mathcal{X}}^{\mathsf{T}} \boldsymbol{Q}_0 - \frac{1}{2} \boldsymbol{Q}_0^{\mathsf{T}} \boldsymbol{\mathcal{X}} \boldsymbol{b} \boldsymbol{\mathcal{X}}^{\mathsf{T}} \boldsymbol{Q}_0,$$

and  $\mathbf{0}^{(k)}$  denotes a vector of k zeros.

In the above, the dot notation denotes time derivative.

PROOF. See Appendix A.1.

The following theorem shows that the solution to (22) is bounded on [0, T], as long as we choose the terminal penalty  $\alpha$  to be large enough.

**Theorem 2.** If  $\frac{1}{2} \mathcal{X} b \mathcal{X}^{T} - \alpha$  is negative definite, the matrix Riccati differential equation (22) has a bounded solution on [0, T].

Proof. See Appendix A.2.

Furthermore, the linear matrix PDEs (24) admit a unique probabilistic representation.

**Theorem 3.** Suppose the assumption of Theorem 2 are enforced, and further  $\mathbb{E}[|\boldsymbol{\mu}_0^{\pm}|^2] < \infty$  and there exists a constant C such that and  $\mathbb{E}_{0,\boldsymbol{\mu}}\left[|\boldsymbol{\mu}_t^{\pm}|^2\right] < C(1+|\boldsymbol{\mu}^{\pm}|^2)$  for all  $t \in [0,T]$ . Let  $\boldsymbol{B}(t,\boldsymbol{\mu})$ ,  $\boldsymbol{D}(t,\boldsymbol{\mu})$  and  $F(t,\boldsymbol{\mu})$  be  $C^{1,2}([0,T),\mathbb{R}^m)$  solutions to (24), each with quadratic growth in  $\boldsymbol{\mu}$ , uniformly in t, then

$$\boldsymbol{D}(t,\boldsymbol{\mu}) = \int_{t}^{T} : \boldsymbol{e}^{\int_{t}^{u} \boldsymbol{C}^{\intercal}(s) \, \boldsymbol{a}^{-1} \, ds} : \left\{ 2 \, \phi \, \tilde{\boldsymbol{\Sigma}} \, \boldsymbol{\mathcal{Q}}_{u} + \, \boldsymbol{\mathcal{X}} \, \bar{\boldsymbol{b}} \, \mathbb{E}_{t,\boldsymbol{\mu}} \left[ \, \boldsymbol{\mu}_{u} \, \right] \right\} \, du \,, \tag{25a}$$

$$\boldsymbol{B}(t,\boldsymbol{\mu}) = \frac{1}{2} \int_{t}^{T} e^{-\boldsymbol{\kappa}(u-t)} \left( \boldsymbol{E}^{\mathsf{T}} - \boldsymbol{\mathcal{X}} \right)^{\mathsf{T}} \boldsymbol{a}^{-1} \mathbb{E} \left[ \boldsymbol{D}(t,\boldsymbol{\mu}_{u}) \right] du, \qquad (25b)$$

$$F(t\,\boldsymbol{\mu}) = \int_{t}^{T} \left\{ \frac{1}{4} \, \mathbb{E}_{t,\boldsymbol{\mu}} \left[ \boldsymbol{D}^{\mathsf{T}}(u,\boldsymbol{\mu}_{u}) \, \boldsymbol{a}^{-1} \, \boldsymbol{D}(u,\boldsymbol{\mu}_{u}) \right] + Tr(\boldsymbol{\Sigma} \, \boldsymbol{A}(u)) - \phi \, \boldsymbol{\mathcal{Q}}_{u}^{\mathsf{T}} \, \tilde{\boldsymbol{\Sigma}} \, \boldsymbol{\mathcal{Q}}_{u} \right\} du \,, \quad (25c)$$

where the notation:  $e^{\int_u^t \cdot ds}$ : represents the time-ordered exponential.<sup>7</sup>

**Theorem 4.** Verification. Suppose the assumptions in Theorem 2 and Theorem 3 are enforced, then the candidate value function (21) is indeed the solution to the control problem. Moreover, the trading rate given by

$$\boldsymbol{\nu}_{t}^{*} = -\frac{1}{2} \boldsymbol{a}^{-1} \left\{ 2 \boldsymbol{C}(t) \boldsymbol{Q}_{t}^{\boldsymbol{\nu}^{*}} + (\boldsymbol{E}^{\mathsf{T}}(t) - \boldsymbol{\mathcal{X}}) (\boldsymbol{S}_{t} - \boldsymbol{\theta}) + \boldsymbol{D}(t, \boldsymbol{\mu}_{t}) \right\}, \tag{26}$$

is admissible and optimal.

<sup>&</sup>lt;sup>7</sup>Recall that the time-ordered exponential of a time dependent matrix  $\mathbf{A}(t)$  is defined as :  $\mathbf{e}(\int_u^t \mathbf{A}(s) \, ds) := \lim_{\|\Pi\| \downarrow 0} \prod_{i=1}^{n_{\Pi}} e^{\mathbf{A}(t_{i-1}) \, \Delta t_i}$ , where  $\Pi := \{u = t_0, t_1, \dots, t_n = t\}$  is a partition of [u, t], and  $\Delta t_i = (t_i - t_{i-1})$ .

The optimal trading rate can be interpreted as the liquidation strategy of AC, plus modifications due to: co-integration, order flow impact, and target inventory. In our setup, we obtain the AC strategy to liquidate a portfolio of m assets by removing co-integration (setting  $\kappa = 0$  in (2)), removing the impact of order flow (setting  $\bar{b} = 0$  in (5)) and setting the target inventory schedule  $\mathcal{Q}_t = \mathbf{0}$  for all  $t \in [0, T]$ . Note that when we trade in all assets, so that m = n,  $\mathcal{X}$  becomes the identity matrix. With these assumptions  $\mathbf{A}(t) = \mathbf{0}^{(n,n)}$ ,  $\mathbf{B}(t) = \mathbf{0}^{(n)}$ ,  $\mathbf{D}(t) = \mathbf{0}^{(m)}$ ,  $\mathbf{E}(t) = \mathbf{I}_m$  (an  $m \times m$  identity matrix), for all  $t \in [0, T]$  in (22). Therefore, the multi-asset AC strategy is to trade at the speed:

$$\nu_t^{AC} = -a^{-1} C(t) Q_t^{\nu^{AC}}. \tag{27}$$

The difference between the optimal trading strategy (26) and the AC strategy consists of two components. The first is  $(E^{\mathsf{T}} - \mathcal{X})$   $(S_t - \theta)$ , which accounts for co-integration in prices, and allows the trader to take advantage of price deviations from all assets – not just the ones she is trading. This modification vanishes as the strategy approaches the end of the trading horizon because the terminal conditions enforce  $E^{\mathsf{T}} \xrightarrow{t \to T} \mathcal{X}$ .

The second component,  $D(t, \mu)$ , is the adjustment due to the inventory target and order flow. For example, if the agent targets zero inventory throughout the life of the strategy,  $Q_t = 0$  for all t, and ignores the effect of order flow from other traders, i.e.  $\bar{b} = 0$ , then  $D(t, \mu)$  vanishes. Moreover, the terminal conditions for D imply that the effect of this adjustment in the trading strategy diminishes as the strategy approaches the terminal date.

As a final point, if the order flow of other agents  $\boldsymbol{\mu}$  is affine, specifically, if  $\mathbb{E}[\boldsymbol{\mu}_u|\mathcal{F}_t] = \boldsymbol{\alpha}(t;u) + \boldsymbol{\beta}(t;u) \, \boldsymbol{\mu}_t$  for some deterministic functions  $\boldsymbol{\alpha}(t;u)$  ( $dim = n \times 1$ ) and  $\boldsymbol{\beta}(t;u)$  ( $dim = n \times n$ ), then the PDE system (24) admits the affine ansatz for  $\boldsymbol{B}(t,\boldsymbol{\mu}) = \boldsymbol{B}_0(t) + \boldsymbol{B}_1(t) \, \boldsymbol{\mu}$  and  $\boldsymbol{D}(t,\boldsymbol{\mu}) = \boldsymbol{D}_0(t) + \boldsymbol{D}_1(t) \, \boldsymbol{\mu}$ , while  $F(t,\boldsymbol{\mu}) = F_0(t) + \boldsymbol{F}_1^{\mathsf{T}}(t) \, \boldsymbol{\mu} + \boldsymbol{\mu}^{\mathsf{T}} \boldsymbol{F}_2(t) \boldsymbol{\mu}$ . Two examples of affine order flow models are (i) the shot-noise processes, where order flow jumps up at Poisson times and mean-reverts back to zero, with idiosyncratic upward and downward jumps, as well as co-jumping order flow; and (ii) the multivariate Hawkes process, where increases in order flow induces excitation in order flow among a subset of assets or all assets. Both of these models have appeared in a number of papers that study the empirical aspects of order flow.

#### 3.2. Guaranteed liquidation

To ensure full liquidation by the end of the trading window, i.e.  $Q_T^{\nu^*} = 0$ , we make the liquidation penalty arbitrarily expensive, i.e. all the components of  $\alpha$  go to  $\infty$ . In this case, the terminal condition for C, see (22), becomes arbitrarily large as the entries of the terminal

condition C(T) go to −∞. Now, let us assume that in this limiting case A, C, and E have the asymptotic series

$$\mathbf{A}(t) = \sum_{n=0}^{\infty} \mathscr{A}_n \, \tau^n \,, \qquad \mathbf{C}(t) = \sum_{n=-1}^{\infty} \mathscr{C}_n \, \tau^n \,, \qquad \mathbf{E}(t) = \sum_{n=0}^{\infty} \mathscr{E}_n \, \tau^n \,, \tag{28}$$

where τ = T − t and An, C<sup>n</sup> and E<sup>n</sup> are constant matrices with the same dimensions as A, C, and E respectively.

The terminal conditions imply that the first term in the asymptotic series A(t) is A<sup>0</sup> = 0 and in E(t) is E<sup>0</sup> = X | . Moreover, substituting (28) into (22), and matching terms with the same power in τ , we obtain the following coefficients for the series of A(t), C(t), and E(t):

$$\mathscr{A}_1 = 0, \quad \mathscr{C}_{-1} = \frac{1}{2} \mathcal{X} b \mathcal{X}^{\mathsf{T}} - a, \quad \mathscr{C}_0 = \mathbf{0}, \quad \mathscr{E}_1 = -\frac{1}{2} \kappa \mathcal{X}^{\mathsf{T}}.$$
 (29)

We also show that the term D(t, µ) in (26) has the asymptotic bound O(τ ) µ + O(τ ). See Appendix A.5 for further details.

Thus, when α → ∞, so that C(T) → −∞ (recall that C(T) = <sup>1</sup> <sup>2</sup> X b X <sup>|</sup> − a from (22)), we employ the asymptotic series (28) (using the first two terms for each series), to write the optimal liquidation speed (26) as follows:

$$\boldsymbol{\nu}_{t}^{*} = \frac{\boldsymbol{Q}_{t}^{\boldsymbol{\nu}^{*}}}{\tau} + \mathcal{O}(\tau) \, \boldsymbol{Z}_{t} + \mathcal{O}(\tau) \, \boldsymbol{\mu} + \mathcal{O}(\tau) \,. \tag{30}$$

The result is that near maturity, i.e. τ → 0, the optimal strategy behaves like TWAP (time-weighted-average-price), which is given by the first term in the right-hand side of (30). Thus, as the strategy approaches the terminal date, the remaining inventory is liquidated at a constant rate.

## 4. Simulations: Portfolio Liquidation

This section shows the performance of the strategy under various assumptions about the set of assets employed by the investor and illustrates how the strategy performs if the investor does not have enough data to calibrate the model parameters. We first describe how the model parameters are estimated using exchange data from five assets traded in Nasdaq. Then we compare the performance of the strategy to that of AC when the agent liquidates a portfolio of two assets: using the information of another additional set of three stocks, using only the information of the two assets, and allowing asset repurchases. In particular, Subsection 4.2.1 assumes that the investor has enough data to correctly estimate the parameters of the model, and Subsection 4.2.2 assumes that the investor does not have access to enough data, so the estimates of the parameters she obtains are incorrect.

#### 4.1. Data and model parameters

To focus on the additional value added by the co-integration information, we turn off the permanent impact from order flow of other agents, i.e. we set  $\bar{b} = 0$ . For an analysis of how agents can benefit from order flow information see Cartea and Jaimungal (2016c). We also turn off the permanent impact from the agent's own trading activity, i.e., we assume b = 0.

We employ high-frequency data from five stocks traded in the Nasdaq exchange: INTC, SMH, FARO, NTAP and ORCL. We use all the messages sent to the exchange in November 3, 2014 to build the LOB at a millisecond frequency. We sample the best quotes and posted volume every 60 seconds during the regular trading hours. Midprices are computed as the weighted average of the best bid and the best ask, with weights equal to the volume posted at the best ask and the best bid respectively – these prices are also referred to as microprice. We remove the first and last half hour to reduce the noise in prices due to the opening and closing auctions. Thus, for the trading day we have a midprice time series of 330 data points per stock.

The five stocks we employ are in the high-tech sector, thus sharing a common trend, so we expect them to be co-integrated. We employ a VAR(1), vector-autoregressive of order 1, model of the joint midprice dynamics which is a discrete-time version of the price process in (5), and apply Johansen's co-integration test to determine the number of co-integrating factors – which corresponds to the rank of the matrix  $\kappa$ . Table 1 reports the p-values of the co-integration test for the number of co-integrating factors, where  $r_i$  corresponds to the null hypothesis that there are at most i co-integrating factors. In Figure 1 we show the realisation

| Model   | $r_0$ | $r_1$ | $r_2$ | $r_3$  | $r_4$ |
|---------|-------|-------|-------|--------|-------|
| p-value | 0.001 | 0.223 | 0.409 | 0.4637 | 0.584 |

Table 1: Johansen's co-integration test for the number of co-integrating factors, and  $r_i$  corresponds to the null hypothesis that there are at most i co-integrating factors. Nasdaq data November 3, 2014.

of this factor through the trading day.

![](_page_12_Figure_7.jpeg)

Figure 1: In-sample path of the calibrated cointegrating factor over the trading day.

Here we choose a midprice model with 1 co-integration factor, and show in the first two rows in Table B.5 the parameter estimates for the mean reverting level θ and the co-integration factors of the VAR(1) model (data November 3, 2014). The rest of the table is taken from Cartea and Jaimungal (2016c) which employs data for the entire year 2014. Rows 3 and 4 are estimates of temporary impact with no cross effects. We choose the temporary impact model with no cross effects to keep our model parsimonious. The bottom 2 rows show the average incoming rates of MOs and their average volume: λ <sup>−</sup> is the average number of sell MO per hour, E[η <sup>−</sup>] is the average volume of sell MOs. The standard deviation of the estimate is shown in parentheses.

Tables B.6 and B.7 show the mean-reverting matrix κ, the variance-covariance matrix Σ, respectively. Time is T = 1, which corresponds to 6.5 hours (1 trading day).

Below we compare the performance of different trading strategies, one of which is AC. In this particular case we assume that midprices satisfy the SDE

$$d\mathbf{P}_t = (\boldsymbol{\sigma}^{AC})^{\mathsf{T}} d\mathbf{W}_t^{AC}. \tag{31}$$

where (σ AC) | is the Cholesky decomposition of the asset prices correlation matrix Σ AC = (σ AC) <sup>|</sup> σ AC. That is, for the AC strategy, asset prices are assumed to be driven by correlated Brownian motions but are not assumed to be co-integrated. Table B.8 shows the estimated correlation matrix Σ AC .

## 4.2. Liquidation of portfolio with two assets

The investor's objective is to liquidate 4,600 shares of INTC and 900 shares of SMH over 1 hour. According to Table B.5, these two numbers correspond to 1% and 4% of the average number of sell volume over 1 hour, respectively. The investor sends MOs at 1 second intervals.

Strategies. To illustrate the performance of the liquidation algorithm we consider the following four strategies:

- 1. Unrestricted liquidation (UL): the strategy ν ∗ t is as in (26) with target schedule Q<sup>t</sup> = 0 for all t. Recall that the investor's set of admissible strategies does not require the trading speed to remain non-negative. So UL may, if it is optimal, repurchase shares before the end of the trading horizon.
- 2. Restricted liquidation (RL): the strategy is as that of UL, but the liquidation speed is set to zero if it is optimal to repurchase, i.e. max (ν ∗ t , 0). This is an ad-hoc adjustment to the optimal strategy to preclude repurchases along the trading window. The max operator max(· , 0) is to be interpreted componentwise: when the speed of liquidation of an asset in the vector (26) is negative, only that component is set to zero. Finally, the strategy stops trading when inventory hits zero. The derivation of the optimal strategy under the constraint ν ∗ <sup>t</sup> ≥ 0 is beyond the scope of our study.

- 3. Unrestricted liquidation with target (ULT): the strategy is as (26) where the target schedule for each asset is the Almgren-Chriss (AC) strategy, i.e., Q<sup>t</sup> = QAC <sup>t</sup> where QAC t is the AC liquidation position given by integrating (27) with penalty parameter φ AC = 0.1.<sup>8</sup> With these parameters, the AC strategy liquidates more than the initial inventory of SMH early on, but repurchases inventory by the trading end. The switching of trading direction is due to the correlation between assets, which causes the trader to take on a hedge-like position to reduce risk.
- 4. Almgren-Chriss liquidation (AC): the strategy is as in (27) and the price process is (31), so the strategy only uses information from INTC and SMH without a co-integrating factor. This is the benchmark we employ to compare the results of the previous three strategies.

Scenarios. We simulate 10<sup>6</sup> sets of sample price paths and look at the performance of the four strategies when liquidating shares in INTC and SMH for a range of values of the penalty parameter φ = 10<sup>−</sup><sup>2</sup> × {0.50 , 0.54 , 0.5833 , 0.63 , 0.6804 , 0.7349 , 0.7937 , 0.8572 , 0.9259 , 1}, and the liquidation penalty is α = 10<sup>6</sup> for both assets, i.e. employ strategies that guarantee full liquidation. We measure the performance by comparing the terminal wealth of UL, RL, ULT, and AC under two scenarios:

- Scenario 1. Liquidate shares in INTC and SMH and employ the additional information provided by three additional assets: FARO, NTAP, ORCL.
- Scenario 2. Liquidate shares in INTC and SMH and only employ the information provided by the dynamics of INTC and SMH.

## 4.2.1. Investor estimates model parameters without error

Figure 2 shows the mean terminal wealth (aggregate cash from liquidating shares in both INTC and SMH) of the four strategies as a function of its standard deviation. As the penalty parameter φ increases, the standard deviation and mean of the terminal wealth decrease. To see the intuition behind this relationship let us focus on UL. The agent targets an inventory of zero throughout the life of the strategy, and the value of φ determines how closely the strategy tracks this target. When the penalty is high, the strategy is less able to trade strategically by either speculating (repurchasing shares) and/or taking advantage of midprice signals that stem from the co-integrating factor. Thus, potential benefits from taking advantage of price movements are outweighed by the requirement that inventory must be drawn to zero very quickly. Conversely, as the penalty becomes smaller, the strategy will have more opportunities

<sup>8</sup>The penalty parameter is embedded in C which appears explicitly in the liquidation speed (27).

![](_page_15_Figure_0.jpeg)

Figure 2: Trading INTC and SMH. Risk-reward for UL, RL, ULT, and AC. Left (right) panel, strategies employ information from all (only the traded) stocks. Within each panel, the penalty  $\phi$  increases moving from the right to the left of the diagrams.

to anticipate and take advantage of midprice movements and these will not be curbed by a strict inventory target.

The left-hand panel of the figure shows Scenario 1 where UL, RL, and ULT employ the additional information provided by FARO, NTAP, ORCL. Clearly, UL dominates the other strategies where AC is the worst performer because it does not account for the co-integration of assets. The right-hand panel of Figure 2 shows Scenario 2 where only information of the co-integrated pair INTC and SMH is employed. Clearly, not employing the additional information provided by other assets that are co-integrated with those in the liquidating portfolio has a considerable effect on the strategies' performance.

Figure 3 shows the mean price per share for INTC and SMH, respectively, for a range of values of the parameter  $\phi$ . For both shares, the figures in the left-hand panels show that including information from other co-integrated assets boosts the performance of UL. The right-hand panel shows that UL is more volatile than the other strategies and this is a result of the strategy speculating on repurchases of the assets.

Table 2 shows, for different values of the target penalty parameter  $\phi$ , how often UL repurchases shares and the percentage of times that UL and RL underperform AC. Here UL and RL employ information of the midprice dynamics of the five co-integrated assets. The table shows that UL's speculative component ranges from 13% to 18% in INTC and 63% to 65% in SMH. UL's speculative trades are similar to those employed in pairs trading, which take advantage of temporary deviations of prices. Moreover, we observe that very seldom do we see UL underperform AC, whereas RL underperforms in around 13% to 14% of the runs. Recall, however, that the optimal strategy we derived is the UL strategy, while RL is an ad-hoc sub-optimal adjustment that precludes asset repurchases.

![](_page_16_Figure_0.jpeg)

Figure 3: Price per share of INTC and SMH for UL, RL, ULT, and AC. Left (right) panels, strategies employ information from all (only the traded) stocks. Within each panel, the penalty  $\phi$  increases moving from the right to the left of the diagrams.

| Strategy              |      | UL     |      |      | RL     |      |
|-----------------------|------|--------|------|------|--------|------|
| $\overline{\phi}$     | 1E-2 | 7.3E-3 | 5E-3 | 1E-2 | 7.5E-3 | 5E-3 |
| $\%\nu_{INTC} < 0$    | 18.7 | 16.3   | 13.0 | 0    | 0      | 0    |
| $%\nu_{SMH} < 0$      | 64.8 | 64.5   | 63.3 | 0    | 0      | 0    |
| $%X_{T} < X_{T}^{AC}$ | 0.2  | 0.4    | 0.9  | 14.2 | 13.9   | 13.4 |

Table 2: Repurchase frequency for UL, and underperformance of UL and RL with respect to AC.

Furthermore, as the value of the parameter  $\phi$  decreases, there are fewer instances in which the liquidation speeds for INTC and SMH are negative. At first this might seem counterintuitive, for one expects a more relaxed penalty parameter to allow UL more freedom to speculate. Note however, that high a value of  $\phi$  (recall that for UL the inventory-target is  $\mathbf{Q}_t = \mathbf{0}$  for all t) pushes the inventory close to zero early. And once the inventory in both assets is low, the strategy attempts more speculative trades by repurchasing the asset. These speculative trades are small in volume, but frequent.

Figure 4 compares the performance of UL and RL with that of AC. The comparison is in

![](_page_17_Figure_0.jpeg)

Figure 4: UL and RL savings in basis points compared to AC. Left (right) panel, strategies employ information from all (only the traded) stocks. Within each panel, the penalty  $\phi$  increases moving from the right to the left of the diagrams.

basis points according to the commonly used metric

$$Savings^{j} = \frac{X_T^j - X_T^{AC}}{X_T^{AC}} \times 10^4, \qquad (32)$$

where  $X_T^j$  is the terminal cash<sup>9</sup> obtained from liquidation the two-asset portfolio employing strategy  $j \in \{\text{UL, RL}\}$ . In the left-hand panel the strategy employs information from the price dynamics of the five co-integrated assets. For UL, savings are in the order of 4 to 4.5 basis points, and for RL between 2.5 and 3.5 basis points. In the right-hand panel, only information provided by the midprice dynamics of the two-asset portfolio is employed, so as expected, the savings are lower.

Finally, Table 3 shows the quantiles of performance of UL and RL measured using (32) for a range of the penalty parameter  $\phi$ . The strategies use the information of the five co-integrated assets.

| Str      | ategy  |      | UL     |      |       | RL     |       |
|----------|--------|------|--------|------|-------|--------|-------|
|          | $\phi$ | 1E-3 | 7.5E-4 | 5E-4 | 1E-3  | 7.5E-4 | 5E-4  |
|          | 5%     | 1.15 | 1.25   | 1.27 | -1.54 | -1.34  | -1.21 |
| ile      | 25%    | 2.77 | 2.60   | 2.55 | 1.16  | 0.96   | 0.84  |
| quantile | 50%    | 4.11 | 3.81   | 3.60 | 3.05  | 2.64   | 2.29  |
| dns      | 75%    | 5.73 | 5.25   | 4.85 | 5.28  | 4.54   | 4.01  |
|          | 95%    | 8.86 | 7.80   | 7.18 | 9.57  | 7.94   | 7.13  |

Table 3: Quantiles of relative savings, measured in basis points using (32).

<sup>&</sup>lt;sup>9</sup>Recall that we have chosen the terminal penalty very large, so that inventory paths end at zero, and hence the terminal cash the agent has equals her wealth from liquidating the shares.

## 4.2.2. Investor estimates model parameters with error

Here we assume that the investor does not have access to enough trading data, so the parameter estimates she obtains are incorrect. The investor observes prices for one day for each asset, which she employs to calibrate the model. The prices she observes are simulated using the parameters in Tables B.6 and B.7. From the observed data, the investor samples prices every minute to estimate parameters, which are reported in Tables B.9 and B.10. Moreover, we use the same set of prices to estimate the coefficients for the benchmark AC strategy – parameter estimates are reported in Table B.11.

To illustrate how the strategy performs when the model parameters are incorrect, we first proceed as above. Then, we simulate 10<sup>6</sup> sets of sample price paths (using the original parameters – so that the agent has incorrect parameters in their trading strategy) and look at the performance of the four strategies when liquidating shares in INTC and SMH, and proceed as in Subsection 4.2. The results are broadly the same as those obtained in the previous section when the investor's parameter estimates where the same as those used to simulate price paths. For example, Table 4 shows quantiles of relative savings, measured in basis points using (32), and parameters are estimated with error. The results in the table are similar to those show above in Table 3 when the investor estimated the parameters of the model without error. Finally, we do not present the analogues to the figures shown above because the results are qualitatively the same.

|          | Strategy |       | UL     |      |       | RL     |       |
|----------|----------|-------|--------|------|-------|--------|-------|
|          | φ        | 1E-2  | 7.5E-3 | 5E-3 | 1E-2  | 7.5E-3 | 5E-3  |
|          | 5%       | 0.47  | 0.77   | 1.05 | -2.12 | -1.90  | -1.72 |
|          | 25%      | 2.90  | 2.82   | 2.80 | 1.23  | 0.97   | 0.87  |
| quantile | 50%      | 4.74  | 4.45   | 4.21 | 3.53  | 3.05   | 2.71  |
|          | 75%      | 6.92  | 6.40   | 5.92 | 6.20  | 5.38   | 4.73  |
|          | 95%      | 11.06 | 9.91   | 8.94 | 11.21 | 9.58   | 8.28  |

Table 4: Quantiles of relative savings, measured in basis points using (32), and parameters are estimated with error.

## 5. Conclusions

We show how to liquidate a basket of assets whose prices are co-integrated. In our framework, market orders from all participants, including the agent liquidating the basket, have a permanent impact on asset prices. In addition, the agent receives prices worse than the best quotes because her trades walk the limit order book, i.e. have temporary price impact. We assume that price impact is linear in the speeds of trading and order flow has cross-effects: trade activity in one asset may have a permanent effect on prices of co-integrated assets and a temporary effect on the limit order books that display the liquidity of the co-integrated assets.

The agent maximizes terminal wealth and targets an inventory schedule. The liquidation strategy employs information from n co-integrated assets and liquidates a basket consisting of a subset of m ≤ n assets. We estimate the model parameters and co-integration factors using trade data from five stocks (INTC, SMH, FARO, NTAP, and ORCL) in the Nasdaq exchange. The agent's basket consists of 4,600 shares in INTC and 900 shares in SMH. We compare the performance of the strategy, under various assumptions, to that of AC where the agent models the correlation between the assets in the basket, but does not model co-integration or employ additional information from other assets.

Our simulations of the liquidation program show that additional information from other co-integrated stocks considerably boosts the performance of the strategy. For example, if the level of urgency required by the agent to liquidate the portfolio is high (resp. low) the strategy outperforms AC by 4 (resp. 4.5) basis points. This improvement over AC is due to the quality of the information provided by the co-integrated assets, and due to a speculative component of the strategy which allows the agent to repurchase shares during the liquidation horizon to take advantage of price signals. If the agent is not allowed to speculate, i.e. cannot repurchase shares, the relative savings compared to AC, depending on the level of urgency, are between 2.5 to 3.5 basis points.

## Appendix A. Proofs

Appendix A.1. Proof of Proposition 1

Proof. Substitute the ansatz (21) into (18), we see that L <sup>ν</sup>H can be simplified to

$$\mathcal{L}^{\nu}H = \boldsymbol{\nu}^{\mathsf{T}} \boldsymbol{a} \boldsymbol{\nu} - \boldsymbol{\nu}^{\mathsf{T}} \left( (\boldsymbol{E}^{\mathsf{T}} - \boldsymbol{\mathcal{X}}) \ \boldsymbol{z} + 2 \boldsymbol{C} \boldsymbol{q} + \boldsymbol{D} \right)$$

$$+ \boldsymbol{\mu}^{\mathsf{T}} \boldsymbol{b}^{\mathsf{T}} \boldsymbol{\mathcal{X}}^{\mathsf{T}} \boldsymbol{q} - \boldsymbol{z}^{\mathsf{T}} (\boldsymbol{\kappa} \boldsymbol{A} + \boldsymbol{A} \boldsymbol{\kappa}^{\mathsf{T}}) \boldsymbol{z} - \boldsymbol{z}^{\mathsf{T}} \boldsymbol{\kappa} (\boldsymbol{E} \boldsymbol{q} + \boldsymbol{B}) + \operatorname{Tr} (\boldsymbol{\Sigma}^{u} \boldsymbol{A}) .$$
(A.1)

The supremum of (A.1) is achieved at

$$\nu^* = -\frac{1}{2}a^{-1}(2Cq + (E^{T} - X)z + D).$$
 (A.2)

Substituting ν ∗ into (18) we obtain the following equality:

$$0 = \mathbf{z}^{\mathsf{T}} \dot{\mathbf{A}} \mathbf{z} + \mathbf{z}^{\mathsf{T}} \left( \dot{\mathbf{B}} + \mathcal{L}^{\mu} \mathbf{B} \right) + \mathbf{q}^{\mathsf{T}} \dot{\mathbf{C}} \mathbf{q} + \mathbf{q}^{\mathsf{T}} \left( \dot{\mathbf{D}} + \mathcal{L}^{\mu} \mathbf{D} \right) + \mathbf{z}^{\mathsf{T}} \dot{\mathbf{E}} \mathbf{q} + \dot{F} + \mathcal{L}^{\mu} F$$

$$-\phi \left( \mathbf{q} - \mathbf{Q}_{t} \right)^{\mathsf{T}} \tilde{\mathbf{\Sigma}} \left( \mathbf{q} - \mathbf{Q}_{t} \right) - \mathbf{z}^{\mathsf{T}} \left( \kappa \mathbf{A} + \mathbf{A} \kappa^{\mathsf{T}} \right) \mathbf{z} - \mathbf{z}^{\mathsf{T}} \kappa \left( \mathbf{E} \mathbf{q} + \mathbf{B} \right) + \operatorname{Tr} \left( \mathbf{\Sigma}^{u} \mathbf{A} \right)$$

$$+ \frac{1}{4} \left( 2 \mathbf{C} \mathbf{q} + (\mathbf{E}^{\mathsf{T}} - \mathbf{X}) \mathbf{z} + \mathbf{D} \right)^{\mathsf{T}} \mathbf{a}^{-1} \left( 2 \mathbf{C} \mathbf{q} + (\mathbf{E}^{\mathsf{T}} - \mathbf{X}) \mathbf{z} + \mathbf{D} \right).$$

Matching the coefficients for z | (·)z, (·) <sup>|</sup>z q<sup>|</sup> (·)q, (·) <sup>|</sup>q, z | (·)q and the constant, and stacking A, C and E we obtain the system of matrix Riccati equations (22) and the linear PDEs (24).

Appendix A.2. Proof of Theorem 2

In this subsection we show that the solution to matrix Riccati equation (22) remains bounded on [0, T]. To show this, we require two intermediate results.

We first state the following comparison theorem (for a proof, see Theorem 2.2.2 in Kratz (2011)).

Theorem 5. Let L1(t), L2(t), M(t), N1(t), N2(t) ∈ R d×d be piecewise continuous on R. Moreover, suppose L1(t), L2(t), N1(t), N2(t) (t ∈ R) and S1, S<sup>2</sup> ∈ R <sup>d</sup>×<sup>d</sup> are symmetric. Let T > 0 and

$${\cal S}_1 \geq {\cal S}_2, \qquad {\cal L}_1 \geq {\cal L}_2 \geq 0, \qquad {\cal N}_1 \geq {\cal N}_2,$$

on [0, T]. Assume that the terminal value problem

$$\dot{H}_1 + H_1 \mathcal{L}_1 H_1 + \mathcal{M} H_1 + H_1 \mathcal{M} + \mathcal{N}_1 = 0, \qquad H_1(T) = \mathcal{S}_1,$$

has a solution H<sup>1</sup> on [0, T]. Then the terminal value problem

$$\dot{H}_2 + H_2 \mathcal{L}_2 H_2 + \mathcal{M} H_2 + H_2 \mathcal{M} + \mathcal{N}_2 = 0, \qquad H_2(T) = \mathcal{S}_2,$$

has a solution H<sup>2</sup> on [0, T] and H1(t) ≥ H2(t) for all t ∈ [0, T].

From the theorem above, we can show the existence of solution to (22) by bounding it by another matrix Riccati differential equation, for which the solution is bounded. The candidate we consider is

$$\dot{\boldsymbol{H}} + \boldsymbol{H}\boldsymbol{M}_{1}\boldsymbol{H} + \boldsymbol{H}\boldsymbol{M}_{2} + \boldsymbol{M}_{2}^{\mathsf{T}}\boldsymbol{H} + \tilde{\boldsymbol{M}}_{3} = \boldsymbol{0}, \tag{A.3}$$

with terminal condition

$$\boldsymbol{H}(T) = \begin{bmatrix} \mathbf{0} & \mathbf{0} & \mathbf{0} \\ \mathbf{0} & \boldsymbol{\chi} b \boldsymbol{\chi}^{\mathsf{T}} - 2 \boldsymbol{\alpha} \end{bmatrix},$$

where M<sup>1</sup> and M<sup>2</sup> are given by (23),

$$\tilde{\boldsymbol{M}}_3 = \begin{bmatrix} \gamma^{max} \boldsymbol{I}_n & \boldsymbol{0} \\ \boldsymbol{0} & \boldsymbol{0} \end{bmatrix},$$

and γ max is the largest eigenvalue of the matrix <sup>1</sup> 2φ κ X <sup>|</sup> Σ˜ −1 X κ | .

The following theorem explicitly characterize the solution of (A.3).

Theorem 6. Suppose α − 1 <sup>2</sup> X b X | is positive definite, the matrix Riccati differential equation (A.3) admits the solution:

$$\boldsymbol{H} = \left[\begin{smallmatrix} \boldsymbol{H}^{11} & \boldsymbol{0} \ \boldsymbol{0} & \boldsymbol{H}^{22} \end{smallmatrix}\right],$$

where H<sup>11</sup> is given by

$$\boldsymbol{H}^{11}(t) = \gamma^{max} \int_{t}^{T} e^{\boldsymbol{\kappa}(t-u)} e^{\boldsymbol{\kappa}^{\mathsf{T}}(t-u)} du, \qquad (A.4)$$

and H<sup>22</sup> is given by

$$\mathbf{H}^{22}(t) = -((T-t)\mathbf{a}^{-1} + (2\alpha - \mathbf{X}b\mathbf{X}^{\mathsf{T}})^{-1})^{-1}.$$
 (A.5)

Proof. First, write H in block form: H(t) = h H11(t) H12(t) H21(t) H22(t) i . From (A.3), it is clear that H<sup>12</sup> = (H<sup>21</sup>) | . Moreover, H<sup>11</sup> , H<sup>12</sup> and H<sup>22</sup> satisfy

$$\dot{\boldsymbol{H}}^{11} + \frac{1}{2}\boldsymbol{H}^{12}\boldsymbol{a}^{-1}\boldsymbol{H}^{21} - \kappa\boldsymbol{H}^{11} - \boldsymbol{H}^{11}\kappa^{\mathsf{T}} + \gamma^{max}\boldsymbol{I}_{n} = \boldsymbol{0}, \qquad (A.6a)$$

$$\dot{\mathbf{H}}^{12} + \frac{1}{2}\mathbf{H}^{12}\mathbf{a}^{-1}\mathbf{H}^{22} = \mathbf{0},$$
 (A.6b)

$$\dot{\mathbf{H}}^{22} + \frac{1}{2}\mathbf{H}^{22}\mathbf{a}^{-1}\mathbf{H}^{22} = \mathbf{0}.$$
 (A.6c)

It is straightforward to verify that (A.5) is a solution to (A.6c). From (A.6b) and the terminal condition, we have H<sup>12</sup>(t) = 0 for all t ≤ T. Moreover (A.6a) becomes

$$\dot{\boldsymbol{H}}^{11} - \kappa \boldsymbol{H}^{11} - \boldsymbol{H}^{11} \kappa^{\intercal} + \gamma^{max} \boldsymbol{I}_n = \boldsymbol{0} \,,$$

whose solution is given by (A.4).

We now state the proof of Theorem 2.

Proof. Theorem 6 asserts that (A.3) has a bounded solution on [0, T], therefore, by applying Theorem 5, it suffices to show that M˜ <sup>3</sup> ≥ M3.

To complete this last step, we decompose (M˜ <sup>3</sup> − M3) as

$$\tilde{\boldsymbol{M}}_{3} - \boldsymbol{M}_{3} = \begin{bmatrix} \gamma^{max} \boldsymbol{I}_{n} & \kappa \boldsymbol{\mathcal{X}}^{\mathsf{T}} \\ \boldsymbol{\mathcal{X}} & \kappa^{\mathsf{T}} & 2\phi \tilde{\boldsymbol{\Sigma}} \end{bmatrix} = \underbrace{\begin{bmatrix} \gamma^{max} \boldsymbol{I}_{n} - \boldsymbol{\Gamma} & \mathbf{0} \\ \mathbf{0} & \mathbf{0} \end{bmatrix}}_{(\mathfrak{A})} + \underbrace{\begin{bmatrix} \boldsymbol{\Gamma} & \kappa \boldsymbol{\mathcal{X}}^{\mathsf{T}} \\ \boldsymbol{\mathcal{X}} & \kappa^{\mathsf{T}} & 2\phi \tilde{\boldsymbol{\Sigma}} \end{bmatrix}}_{(\mathfrak{B})},$$

where Γ = 1 2φ κ X <sup>|</sup> Σ˜ −1 X κ | . Recall that γ max is the largest eigenvalue of Γ, hence (A) is positive semidefinite. It remains to prove that (B) is positive semidefinite as well.

For any w ∈ R <sup>n</sup>+<sup>m</sup>, write w = [w | 1 , w | 2 ] <sup>|</sup> where w<sup>1</sup> ∈ R <sup>n</sup> and w<sup>2</sup> ∈ R <sup>m</sup>, then we have

$$\begin{split} & \boldsymbol{w}^{\intercal} \begin{bmatrix} \boldsymbol{\Gamma} & \boldsymbol{\kappa} \boldsymbol{\mathcal{X}}^{\intercal} \\ \boldsymbol{\mathcal{X}} \boldsymbol{\kappa}^{\intercal} & 2\phi \tilde{\boldsymbol{\Sigma}} \end{bmatrix} \boldsymbol{w} \\ &= \boldsymbol{w}_{1}^{\intercal} \boldsymbol{\Gamma} \boldsymbol{w}_{1} + 2 \boldsymbol{w}_{2}^{\intercal} \boldsymbol{\mathcal{X}} \boldsymbol{\kappa}^{\intercal} \boldsymbol{w}_{1} + 2\phi \boldsymbol{w}_{2}^{\intercal} \tilde{\boldsymbol{\Sigma}} \boldsymbol{w}_{2} \\ &= \boldsymbol{w}_{1}^{\intercal} \boldsymbol{\Gamma} \boldsymbol{w}_{1} + 2 \left( \sqrt{2\phi} \, \tilde{\boldsymbol{\sigma}} \, \boldsymbol{w}_{2} \right)^{\intercal} \left( \frac{(\tilde{\boldsymbol{\sigma}}^{-1})^{\intercal}}{\sqrt{2\phi}} \boldsymbol{\mathcal{X}} \, \boldsymbol{\kappa}^{\intercal} \, \boldsymbol{w}_{1} \right) + \left( \sqrt{2\phi} \, \tilde{\boldsymbol{\sigma}} \, \boldsymbol{w}_{2} \right)^{\intercal} \left( \sqrt{2\phi} \, \tilde{\boldsymbol{\sigma}} \, \boldsymbol{w}_{2} \right) \\ &= \left( \frac{(\tilde{\boldsymbol{\sigma}}^{-1})^{\intercal}}{\sqrt{2\phi}} \, \boldsymbol{\mathcal{X}} \, \boldsymbol{\kappa}^{\intercal} \boldsymbol{w}_{1} + \sqrt{2\phi} \, \tilde{\boldsymbol{\sigma}} \, \boldsymbol{w}_{2} \right)^{\intercal} \left( \frac{(\tilde{\boldsymbol{\sigma}}^{-1})^{\intercal}}{\sqrt{2\phi}} \, \boldsymbol{\mathcal{X}} \, \boldsymbol{\kappa}^{\intercal} \, \boldsymbol{w}_{1} + \sqrt{2\phi} \, \tilde{\boldsymbol{\sigma}} \, \boldsymbol{w}_{2} \right) \\ &\geq 0 \, . \end{split}$$

This implies that (B) is positive semidefinite and by the comparison principle of Theorem 5, the proof is complete.

## Appendix A.3. Proof of Theorem 3

To prove the result, we need to show that (25a) is the unique solution to (24b). To do this we introduce a sequence of approximating functions that converge to the stated solution.

Let  $\Pi = \{t = t_0, t_1, \dots, t_{n_{\Pi}} = T\}$  be a partition of [0, T], let  $|\Pi|$  denote the cardinality of the partition  $\Pi$ , and let  $\Delta t_k = (t_k - t_{k-1})$ . Next, introduce the following piecewise (left continuous with right limits) constant approximation of  $\widetilde{\boldsymbol{C}}(t) \triangleq \boldsymbol{C}^{\intercal}(t) \boldsymbol{a}^{-1}$ ,

$$\widetilde{\boldsymbol{C}}^\Pi(t) := \sum_{k=1}^{|\Pi|} \boldsymbol{C}^\intercal(t_k) \, \boldsymbol{a}^{-1} \, \mathbb{1}_{\{t \in (t_{k-1},t_k]\}} \, .$$

The time-ordered exponential of  $\widetilde{\boldsymbol{C}}^{\Pi}(t)$  is given by

$$: e^{\int_t^u \tilde{\boldsymbol{C}}^{\Pi}(s) ds} := e^{\tilde{\boldsymbol{C}}^{\Pi}(t_k)(t_k - t)} \left[ \prod_{j=k+1}^l e^{\tilde{\boldsymbol{C}}^{\Pi}(t_j)\Delta t_j} \right] e^{\tilde{\boldsymbol{C}}^{\Pi}(t_{l+1})(u - t_l)}, \tag{A.7}$$

 $\forall t \in [t_{k-1}, t_k]$ , and  $u \in [t_l, t_{l+1}]$ ,  $l < |\Pi|$ . Note that this is continuous in both t and u for all  $t < u \in [0, T]$ . We next define a sequence of functions

$$\boldsymbol{D}^{\Pi}(t,\boldsymbol{\mu}) = \mathbb{E}_{t,\boldsymbol{\mu}} \left[ \int_{t}^{T} : e^{\int_{t}^{u} \tilde{\boldsymbol{C}}^{\Pi}(s) \, ds} : \, \mathfrak{Z}_{u} \, du \right], \tag{A.8}$$

where we have introduced the process  $\mathfrak{Z} = (\mathfrak{Z}_t)_{t \in [0,T]}$  and

$$\mathbf{\beta}_t = \boldsymbol{\zeta}(t, \boldsymbol{\mu}_t)$$
 where  $\boldsymbol{\zeta}(t, \boldsymbol{\mu}) = 2 \phi \; \tilde{\boldsymbol{\Sigma}} \; \boldsymbol{Q}_t + \; \boldsymbol{\mathcal{X}} \; \overline{\boldsymbol{b}} \; \boldsymbol{\mu}$ .

We require the following proposition to proceed.

**Proposition 7.** PDE for approximating functions. The function  $\mathbf{D}^{\Pi}(t, \boldsymbol{\mu})$  is the unique solution to the vector-valued PDE

$$\dot{\boldsymbol{D}}^{\Pi} + \mathcal{L}^{\mu} \boldsymbol{D}^{\Pi} + \widetilde{\boldsymbol{C}}^{\Pi} \boldsymbol{D}^{\Pi} + \boldsymbol{\zeta}(t, \mu) = \mathbf{0}^{(m)}$$
(A.9)

with terminal condition  $\mathbf{D}^{\Pi}(T, \boldsymbol{\mu}) = \mathbf{0}^{(m)}$ .

PROOF. To show this, define the stochastic process  $\mathfrak{D}^{\Pi} = (\mathfrak{D}_t^{\Pi})_{t \in [0,T]}$ , where

$$\boldsymbol{\mathfrak{D}}_t^{\Pi} = : \boldsymbol{e}^{\int_0^t \widetilde{\boldsymbol{C}}^{\Pi}(s) \, ds} : \boldsymbol{D}^{\Pi}(t, \boldsymbol{\mu}_t) + \int_0^t : \boldsymbol{e}^{\int_0^u \widetilde{\boldsymbol{C}}^{\Pi}(s) \, ds} : \boldsymbol{\mathfrak{Z}}_u \, du \, .$$

Due the Markov property of  $\mu$ , we see that

$$\boldsymbol{\mathfrak{D}}_t^{\Pi} = \mathbb{E}\left[\int_0^T: e^{\int_0^u \widetilde{\boldsymbol{C}}^{\Pi}(s) \, ds} \colon \boldsymbol{\mathfrak{Z}}_u \, du \, \middle| \, \mathcal{F}_t^{\boldsymbol{\mu}}\right].$$

By the integrability assumptions on the process  $\mu$ , this is a strict martingale. Moreover, the Markov property implies the existence of a sequence of functions  $\mathbf{f}^{\Pi}: \mathbb{R}_{+} \times \mathbb{R} \mapsto \mathbb{R}$  such that  $\mathfrak{D}_{t}^{\Pi} = \mathbf{f}^{\Pi}(t, \mu_{t})$ . For any  $\mathcal{F}^{\mu}$ -stopping time  $\tau \leq T$ , by Dynkin's formula we have

$$\begin{aligned} \mathbf{0}^{(m)} &= \mathbb{E}[\mathbf{D}_{\tau}^{\Pi} - \mathbf{D}_{t}^{\Pi} \mid \mathcal{F}_{t}^{\boldsymbol{\mu}}] \\ &= \mathbb{E}\left[\int_{t}^{\tau} \left\{\partial_{t} \mathbf{f}^{\Pi}(u, \boldsymbol{\mu}_{u}) + \mathcal{L}^{\boldsymbol{\mu}} \mathbf{f}^{\Pi}(u, \boldsymbol{\mu}_{u})\right\} du \mid \mathcal{F}_{t}^{\boldsymbol{\mu}}\right]. \end{aligned}$$

Taking  $\tau = (T - t) \wedge h \wedge \inf\{s \geq 0 : |\boldsymbol{\mu}_{t+s} - \boldsymbol{\mu}_t| \geq \epsilon\}$ , for h small, then

$$\mathbf{0}^{(m)} = \mathbb{E}\left[\frac{1}{h} \int_{t}^{\tau} \left\{ \partial_{t} \mathbf{f}^{\Pi}(u, \boldsymbol{\mu}_{u}) + \mathcal{L}^{\boldsymbol{\mu}} \mathbf{f}^{\Pi}(u, \boldsymbol{\mu}_{u}) \right\} du \,\middle|\, \mathcal{F}_{t}^{\boldsymbol{\mu}} \right]. \tag{A.10}$$

As  $h \downarrow 0$ ,  $\mathbb{P}(\tau \neq h) \downarrow 0$ , thus taking the limit as  $h \downarrow 0$ , and using the fundamental theorem of calculus, we have

$$\partial_t \mathbf{f}^{\Pi}(t, \boldsymbol{\mu}_t) + \mathcal{L}^{\boldsymbol{\mu}} \mathbf{f}^{\Pi}(t, \boldsymbol{\mu}_t) = \mathbf{0}^{(m)}. \tag{A.11}$$

Furthermore, from (A.7),

$$\partial_t \mathbf{f}^\Pi(t,\boldsymbol{\mu}_t) = : \boldsymbol{e}^{\int_0^t \widetilde{\boldsymbol{C}}^\Pi(s) \, ds} : \left\{ \widetilde{\boldsymbol{C}}^\Pi(t) \, \boldsymbol{D}^\Pi(t,\boldsymbol{\mu}_t) + \partial_t \boldsymbol{D}^\Pi(t,\boldsymbol{\mu}_t) + \boldsymbol{\zeta}(t,\boldsymbol{\mu}_t) \right\}$$

and  $\mathcal{L}^{\mu}\mathfrak{f}^{\Pi}(t,\boldsymbol{\mu}_{t}) = : \boldsymbol{e}^{\int_{0}^{t} \tilde{\boldsymbol{C}}^{\Pi}(s) \, ds} : \mathcal{L}^{\mu}\boldsymbol{D}^{\Pi}(t,\boldsymbol{\mu}_{t})$ , hence, since (A.11) holds for all paths of  $\boldsymbol{\mu}$ , together with these two equalities, (A.11) reduces to (A.9).

Now, define the approximation error  $\mathfrak{E}^{\Pi}(t, \boldsymbol{\mu}) \triangleq \boldsymbol{D}^{\Pi}(t, \boldsymbol{\mu}) - \boldsymbol{D}(t, \boldsymbol{\mu})$ . Taking the difference between (24b) and (A.9), we see that  $\mathfrak{E}^{\Pi}$  satisfies the linear PDE

$$\left(\partial_t + \mathcal{L}^{\boldsymbol{\mu}}\right)\mathfrak{E}^\Pi(t,\boldsymbol{\mu}) + \widetilde{\boldsymbol{C}}^\Pi(t)\mathfrak{E}^\Pi(t,\boldsymbol{\mu}) + \left(\widetilde{\boldsymbol{C}}^\Pi(t) - \widetilde{\boldsymbol{C}}(t)\right)\boldsymbol{D}(t,\boldsymbol{\mu}) = \boldsymbol{0}^{(m)}\,,$$

with terminal condition  $\mathfrak{E}^{\Pi}(T, \boldsymbol{\mu}) = \mathbf{0}^{(m)}$ . Applying the same argument as above,  $\mathfrak{E}^{\Pi}$  admits the representation

$$\mathfrak{E}^{\Pi}(t,\boldsymbol{\mu}) = \mathbb{E}_{t,\boldsymbol{\mu}} \left[ \int_{t}^{T} : \boldsymbol{e}^{\int_{t}^{u} \widetilde{\boldsymbol{C}}^{\Pi}(s) \, ds} : \left( \widetilde{\boldsymbol{C}}^{\Pi}(s) - \widetilde{\boldsymbol{C}}(s) \right) \, \boldsymbol{D}(s,\boldsymbol{\mu}_{s}) \, du \right]. \tag{A.12}$$

It remains to show  $\mathfrak{E}^{\Pi}(t,\boldsymbol{\mu}) \xrightarrow{\Pi\downarrow 0} \mathbf{0}$ . By Theorem 2,  $\boldsymbol{C}$  is bounded and continuous on [0,T]. Therefore, by construction,  $\tilde{\boldsymbol{C}}$ ,  $\tilde{\boldsymbol{C}}^{\Pi}$  and  $: \boldsymbol{e}^{\int_t^u \tilde{\boldsymbol{C}}^{\Pi}(s) \, ds} :$  are all bounded and we have  $\tilde{\boldsymbol{C}}^{\Pi} \xrightarrow{\Pi\downarrow 0} \tilde{\boldsymbol{C}}$ . By the assumptions, there exists a constant  $C_2 > 0$  such that

$$|D(t,\boldsymbol{\mu})| \le C_2(1+|\boldsymbol{\mu}|^2)$$

for all  $t \in [0,T]$ . The assumptions on  $\boldsymbol{\mu}^{\pm}$  imply that  $\boldsymbol{\mu}$  has a finite  $\mathbb{L}^2(\Omega \times [0,T))$ -norm. Hence  $\boldsymbol{D} := \{\boldsymbol{D}(t,\boldsymbol{\mu}_t)\}_{0 \le t \le T}$  has a finite  $\mathbb{L}^1(\Omega \times [0,T))$ -norm. The desired result follows from dominated convergence.

PROOF. Under the stated assumptions, the candidate solution is indeed a classical solution of the DPE. Applying standard results (e.g., Øksendal and Sulem (2005)), it suffices to check that: (i) the SDE for  $Q^{\nu^*}$  has a unique solution for each given initial data; and (ii)  $\nu_t^*$  is indeed an admissible control.

To verify (i), substituting the optimal control (26) into the dynamics of (3), we have the dynamics for  $\mathbf{Q}_t^{\nu^*}$ :

$$d\boldsymbol{Q}_{t}^{\boldsymbol{\nu}^{*}} = -\frac{1}{2}\boldsymbol{a}^{-1}\left(2\,\boldsymbol{C}(t)\,\boldsymbol{Q}_{t}^{\boldsymbol{\nu}^{*}} + \left(\boldsymbol{E}^{\intercal}(t) - \boldsymbol{\mathcal{X}}\right)\,\boldsymbol{Z}_{t} + \boldsymbol{D}(t, \boldsymbol{\mu}_{t})\right)\,dt\,.$$

The above equation is an ODE with stochastic source term, and it can be explicitly integrated to find

$$Q_t^{\boldsymbol{\nu}^*} = : e^{-\int_0^t a^{-1} \boldsymbol{C}(s) \, ds} : Q_0$$

$$-\int_0^t : e^{-\int_u^t a^{-1} \boldsymbol{C}(s) \, ds} : \left\{ (\boldsymbol{E}^{\mathsf{T}}(u) - \boldsymbol{\mathcal{X}}) \; \boldsymbol{Z}_u + \boldsymbol{D}(u, \boldsymbol{\mu}_u) \right\} du . \tag{A.13}$$

Therefore,  $Q^{\nu^*}$  has a unique solution for any initial data.

To verify (ii), it suffices to show that  $\boldsymbol{\nu}_t^*$  has a finite  $\mathbb{L}^2(\Omega \times [0,T))$ -norm. From (26), it suffices to show that each of  $\boldsymbol{Z}$ ,  $\boldsymbol{Q}^{\boldsymbol{\nu}^*}$  and  $\boldsymbol{D} := \{\boldsymbol{D}(t,\boldsymbol{\mu}_t)\}_{0 \leq t \leq T}$  has a finite  $\mathbb{L}^2(\Omega \times [0,T))$ -norm. From the SDE (5) we see that  $\boldsymbol{Z}$  satisfies this condition. Moreover, from (A.13) and Theorem 2 which implies that  $\boldsymbol{C}$  and  $\boldsymbol{E}$  are bounded on [0,T],  $\boldsymbol{Q}$  has a finite  $\mathbb{L}^2(\Omega \times [0,T))$ -norm if  $\boldsymbol{D}$  does.

It remains to show that  $\mathbf{D}$  has a finite  $\mathbb{L}^2(\Omega \times [0,T))$ -norm. From (25a) and the assumptions in Theorem 2, there exists a constant  $C_2 > 0$  such that

$$|\boldsymbol{D}(t,\boldsymbol{\mu})| \leq C_2(1+|\boldsymbol{\mu}|),$$

for all  $0 \le t \le T$  and  $\boldsymbol{\mu} \in \mathbb{R}^n$ . Furthermore, since the assumptions imply that  $\boldsymbol{\mu}$  has a finite  $\mathbb{L}^2(\Omega \times [0,T))$ -norm,  $\boldsymbol{D}$  also has a finite  $\mathbb{L}^2(\Omega \times [0,T))$ -norm, and the desired result follows.

Substituting the power series representation (28) into the matrix differential equations (22), we obtain the following equations

$$\mathbf{0} = -\sum_{n=0}^{\infty} (n+1) \,\mathcal{A}_{n+1} \,\tau^n - \sum_{n=1}^{\infty} \left[ \boldsymbol{\kappa} \,\mathcal{A}_n + \mathcal{A}_n \,\boldsymbol{\kappa}^{\mathsf{T}} \right] \,\tau^n + \left[ \frac{1}{4} \sum_{n=1}^{\infty} \mathcal{E}_n \,\tau^n \right] \boldsymbol{a}^{-1} \left[ \sum_{n=1}^{\infty} \mathcal{E}_n^{\mathsf{T}} \,\tau^n \right], \qquad (A.14a)$$

$$\mathbf{0} = \frac{\mathscr{C}_{-1}}{\tau^2} - \sum_{n=0}^{\infty} (n+1) \mathscr{C}_{n+1} \tau^n - \phi \,\tilde{\mathbf{\Sigma}} + \left[ \frac{\mathscr{C}_{-1}^{\mathsf{T}}}{\tau} + \sum_{n=0}^{\infty} \mathscr{C}_n^{\mathsf{T}} \tau^n \right] \mathbf{a}^{-1} \left[ \frac{\mathscr{C}_{-1}}{\tau} + \sum_{n=0}^{\infty} \mathscr{C}_n \tau^n \right], \quad (A.14b)$$

$$\mathbf{0} = -\sum_{n=0}^{\infty} (n+1) \,\mathcal{E}_{n+1} \,\tau^n - \sum_{n=0}^{\infty} \boldsymbol{\kappa} \,\mathcal{E}_n \,\tau^n + \left[\sum_{n=1}^{\infty} \mathcal{E}_n \,\tau^n\right] \mathbf{a}^{-1} \left(\frac{\mathcal{E}_{-1}}{\tau} + \sum_{n=0}^{\infty} (\mathcal{E}_n) \,\tau^n\right). \tag{A.14c}$$

Matching the constant terms in (A.14a), we have A<sup>1</sup> = 0. Matching the coefficients for τ −2 in (A.14b), we have C<sup>−</sup><sup>1</sup> = −a. Matching the coefficients for τ −1 in (A.14b) yields the following equality

$$\mathscr{C}_{-1} \boldsymbol{a}^{-1} \mathscr{C}_0 + \mathscr{C}_0 \boldsymbol{a}^{-1} \mathscr{C}_{-1} = \boldsymbol{0}$$
.

Therefore C<sup>0</sup> = 0.

Finally, by matching the constant terms in (A.14c):

$$-\mathscr{E}_1 - \boldsymbol{\kappa}\,\boldsymbol{\mathcal{X}}^{\intercal} + \mathscr{E}_1\,\boldsymbol{a}^{-1}\,\mathscr{C}_{-1} = 0\,.$$

This implies E<sup>1</sup> = − 1 2 κ X | .

It remains to show that D(t, µ) admits the asymptotic representation O(τ )µ + O(τ ). From the assumptions in Theorem 3, we have E0,<sup>µ</sup> [|µ<sup>t</sup> |] < C (1 + |µ|) for all 0 ≤ t ≤ T and some constant C > 0. Since we assume that µ is Markov, we also have

$$\boldsymbol{E}_{t,\boldsymbol{\mu}}\left[|\boldsymbol{\mu}_u|\right] < C \left(1 + |\boldsymbol{\mu}|\right)$$
,

for 0 ≤ t ≤ u ≤ T. The above bound, together with (25a), yields

$$|D(t,\boldsymbol{\mu})| \leq \int_{t}^{T} C_{2} + C_{3} |\boldsymbol{\mu}| du,$$

for constants C2, C<sup>3</sup> > 0. The desired result follows.

## Appendix B. Parameter Estimates

In this appendix we collect the various parameter estimates from the five Nasdaq traded stocks INTC, SMH, FARO, NTAP and ORCL.

|               | INTC         | SMH          | FARO         | NTAP         | ORCL         |
|---------------|--------------|--------------|--------------|--------------|--------------|
| ˆθ            | 34.233       | 51.720       | 56.338       | 43.179       | 38.885       |
| Co-int factor | -0.904       | 0.763        | 0.048        | -0.164       | 0.931        |
| aˆ            | 0.44 × 10−6  | 0.71 × 10−6  | 0.32 × 10−3  | 3.05 × 10−6  | 1.35 × 10−6  |
|               | (2.37 × 10−7 | (2.58 × 10−7 | (1.62 × 10−4 | (1.27 × 10−6 | (0.56 × 10−6 |
|               | )            | )            | )            | )            | )            |
| λˆ−           | 453.91       | 59.4         | 21.88        | 251.87       | 304.13       |
|               | (264.63)     | (49.46)      | (9.25)       | (102.72)     | (146.83)     |
| E[η           | 1013.83      | 380.32       | 98.58        | 270.8        | 505.59       |
| −]            | (306.58)     | (121.39)     | (15.78)      | (55.2)       | (100.29)     |

Table B.5: First two rows (data November 3, 2014) show mean-reverting level θ (in dollars) and weights of the co-integrating factor. Rest of table employs data for the entire year 2014. Row 3 shows the estimates of temporary price impact. We assume no cross effects so only provide the diagonal elements of the matrix a, and recall we assume no permanent impact. Row 4 shows the standard deviation of the estimates in row 3. The bottom 4 rows show the average incoming rates of MOs and their average volume: λ <sup>−</sup> is the average number of sell MO per hour over the year 2014, E[η <sup>−</sup>] is the average volume of MOs. The standard deviation of the estimate is shown in parentheses.

|      | INTC    | SMH     | FARO   | NTAP   | ORCL    |
|------|---------|---------|--------|--------|---------|
| INTC | 45.66   | -38.51  | -2.43  | 8.26   | -47.01  |
|      | (10.70) | (8.99)  | (0.57) | (1.93) | (11.02) |
| SMH  | -19.83  | 16.73   | 1.06   | -3.59  | 20.42   |
|      | (13.42) | (11.27) | (0.72) | (2.41) | (13.82) |
| FARO | -41.34  | 34.87   | 2.20   | -7.48  | 42.57   |
|      | (51.50) | (43.27) | (2.75) | (9.27) | (53.05) |
| NTAP | 4.98    | -4.20   | -0.27  | 0.90   | -5.13   |
|      | (12.17) | (10.22) | (0.65) | (2.19) | (12.54) |
| ORCL | -6.47   | 5.45    | 0.34   | -1.17  | 6.66    |
|      | (6.30)  | (5.29)  | (0.34) | (1.14) | (6.49)  |

Table B.6: Estimated mean-reverting matrix κ and t statistics.

|      | INTC   | SMH   | FARO   | NTAP  | ORCL  |
|------|--------|-------|--------|-------|-------|
| INTC | 0.124  | 0.108 | -0.040 | 0.027 | 0.019 |
| SMH  | 0.108  | 0.194 | 0.060  | 0.060 | 0.027 |
| FARO | -0.040 | 0.060 | 2.855  | 0.058 | 0.001 |
| NTAP | 0.027  | 0.060 | 0.058  | 0.159 | 0.022 |
| ORCL | 0.020  | 0.027 | 0.001  | 0.022 | 0.043 |

Table B.7: Estimated covariance matrix Σ.

|      | INTC  | SMH   |
|------|-------|-------|
| INTC | 0.131 | 0.105 |
| SMH  | 0.105 | 0.195 |

Table B.8: Estimated covariance matrix Σ AC .

|      | INTC    | SMH     | FARO   | NTAP    | ORCL    |
|------|---------|---------|--------|---------|---------|
| INTC | 73.92   | -62.79  | -3.50  | 19.57   | -77.42  |
|      | (10.99) | (9.34)  | (0.52) | (2.93)  | (11.50) |
| SMH  | 8.91    | -7.57   | -0.42  | 2.36    | -9.33   |
|      | (14.25) | (12.11) | (0.67) | (3.79)  | (14.93) |
| FARO | 48.73   | -41.39  | -2.31  | 12.90   | -51.04  |
|      | (50.80) | (43.18) | (2.40) | (13.53) | (53.20) |
| NTAP | 11.48   | -9.75   | -0.54  | 3.04    | -12.02  |
|      | (12.25) | (10.41) | (0.58) | (3.26)  | (12.83) |
| ORCL | -15.83  | 13.45   | 0.75   | -4.19   | 16.59   |
|      | (6.39)  | (5.44)  | (0.30) | (1.70)  | (6.70)  |

Table B.9: Estimated (with error) mean-reverting matrix κ and t statistics.

|      | INTC   | SMH   | FARO   | NTAP  | ORCL   |
|------|--------|-------|--------|-------|--------|
| INTC | 0.155  | 0.155 | -0.032 | 0.053 | 0.032  |
| SMH  | 0.155  | 0.260 | 0.061  | 0.084 | 0.033  |
| FARO | -0.032 | 0.061 | 3.299  | 0.144 | -0.006 |
| NTAP | 0.053  | 0.084 | 0.144  | 0.192 | 0.021  |
| ORCL | 0.032  | 0.033 | -0.006 | 0.021 | 0.053  |

Table B.10: Estimated (with error) covariance matrix Σ.

|      | INTC  | SMH   |
|------|-------|-------|
| INTC | 0.169 | 0.160 |
| SMH  | 0.160 | 0.261 |

Table B.11: Estimated (with error) covariance matrix Σ AC .

## References

- Alfonsi, A., A. Fruth, and A. Schied (2010). Optimal execution strategies in limit order books with general shape functions. Quantitative Finance 10(2), 143–157.
- Almgren, R. (2003). Optimal execution with nonlinear impact functions and trading-enhanced risk. Applied Mathematical Finance 10(1), 1–18.
- Almgren, R. (2012). Optimal trading with stochastic liquidity and volatility. SIAM Journal on Financial Mathematics 3(1), 163–181.
- Almgren, R. (2014). High Frequency Trading; New Realities for Trades, Markets and Regulators, Chapter Execution Strategies in Fixed Income Markets. Eds: Easley, D. and L´opez de Prado, M. and M. O'Hara. Risk Books.
- Almgren, R. and N. Chriss (2001). Optimal execution of portfolio transactions. Journal of Risk 3, 5–40.
- Bank, P., H. M. Soner, and M. Voß (2015). Hedging with temporary price impact. Mathematics and Financial Economics, 1–25.
- Bayraktar, E. and M. Ludkovski (2014, October). Liquidation in limit order books with controlled intensity. Mathematical Finance 24(4), 627–650.
- Cartea, A., R. Donnelly, and S. Jaimungal (2013). Algorithmic trading with model uncer- ´ tainty. SSRN: http://ssrn.com/abstract=2310645.
- Cartea, A. and S. Jaimungal (2015). Optimal execution with limit and market orders. ´ Quantitative Finance 15(8), 1279–1291.
- Cartea, A. and S. Jaimungal (2016a). Algorithmic trading of co-integrated assets. ´ International Journal of Theoretical and Applied Finance 19(06), 1650038.
- Cartea, A. and S. Jaimungal (2016b). A closed-form execution strategy to target volume ´ weighted average price. SIAM Journal on Financial Mathematics 7(1), 760–785.
- Cartea, A. and S. Jaimungal (2016c). Incorporating order-flow into optimal execution. ´ Mathematics and Financial Economics 10(3), 339–364.
- Cartea, A., S. Jaimungal, and D. Kinzebulatov (2016). Algorithmic trading with learning. ´ International Journal of Theoretical and Applied Finance 19(04), 1650028.
- Cartea, A., S. Jaimungal, and J. Penalva (2015). ´ Algorithmic and High-Frequency Trading (1st ed.). Cambridge: Cambridge University Press.
- Forsyth, P. A., J. S. Kennedy, S. Tse, and H. Windcliff (2012). Optimal trade execution: a mean quadratic variation approach. Journal of Economic Dynamics and Control 36(12), 1971–1991.

- Gˆarleanu, N. and L. Pedersen (2013). Dynamic trading with predictable returns and transaction costs. The Journal of Finance 68(6), 2309–2340.
- Gatheral, J., A. Schied, and A. Slynko (2012). Transient linear price impact and Fredholm integral equations. Mathematical Finance 22(3), 445–474.
- Gu´eant, O. and C.-A. Lehalle (2015). General intensity shapes in optimal liquidation. Mathematical Finance 25(3), 457–495.
- Gu´eant, O., C.-A. Lehalle, and J. Fernandez Tapia (2012). Optimal portfolio liquidation with limit orders. SIAM Journal on Financial Mathematics 3(1), 740–764.
- Guilbaud, F. and H. Pham (2013). Optimal high-frequency trading with limit and market orders. Quantitative Finance 13(1), 79–94.
- Jaimungal, S. and D. Kinzebulatov (2013). Optimal execution with a price limiter. Available at SSRN 2199889.
- Kharroubi, I. and H. Pham (2010a). Optimal portfolio liquidation with execution cost and risk. SIAM Journal on Financial Mathematics 1(1), 897–931.
- Kharroubi, I. and H. Pham (2010b). Optimal portfolio liquidation with execution cost and risk. SIAM Journal on Financial Mathematics 1(1), 897–931.
- Kratz, D.-M. P. (2011). Optimal liquidation in dark pools in discrete and continuous time. Ph. D. thesis, Humboldt-Universit¨at zu Berlin.
- Lei, Y. and J. Xu (2015). Costly arbitrage through pairs trading. Journal of Economic Dynamics and Control 56, 1–19.
- Leung, T. and X. Li (2015). Optimal mean reversion trading with transaction costs and stop-loss exit. International Journal of Theoretical and Applied Finance, 1550020.
- Lintilhac, P. and A. Tourin (2016). Model-based pairs trading in the bitcoin markets. Quantitative Finance, 1–14.
- Mudchanatongsuk, S., J. A. Primbs, and W. Wong (2008). Optimal pairs trading: A stochastic control approach. In American Control Conference, 2008, pp. 1035–1039. IEEE.
- Ngo, M.-M. and H. Pham (2016). Optimal switching for the pairs trading rule: A viscosity solutions approach. Journal of Mathematical Analysis and Applications 441(1), 403 – 425.
- Øksendal, B. K. and A. Sulem (2005). Applied stochastic control of jump diffusions, Volume 498. Springer.
- Passerini, F. and S. Vazquez (2016). Optimal trading with alpha predictors. Journal of Investment Strategies 5(3), 2047–1238.

- Schied, A. (2013). Robust strategies for optimal order execution in the Almgren—Chriss framework. Applied Mathematical Finance 20(3), 264–286.
- Tourin, A. and R. Yan (2013). Dynamic pairs trading using the stochastic control approach. Journal of Economic Dynamics and Control 37(10), 1972 – 1981.