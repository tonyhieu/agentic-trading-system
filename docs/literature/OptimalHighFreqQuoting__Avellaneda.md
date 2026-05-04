![](_page_0_Picture_2.jpeg)

![](_page_0_Picture_3.jpeg)

# High-frequency trading in a limit order book

MARCO AVELLANEDA and SASHA STOIKOV\*

Mathematics, New York University, 251 Mercer Street, New York, NY 10012, USA

(Received 24 April 2006; in final form 3 April 2007)

# 1. Introduction

The role of a dealer in securities markets is to provide liquidity on the exchange by quoting bid and ask prices at which he is willing to buy and sell a specific quantity of assets. Traditionally, this role has been filled by marketmaker or specialist firms. In recent years, with the growth of electronic exchanges such as Nasdaq's Inet, anyone willing to submit limit orders in the system can effectively play the role of a dealer. Indeed, the availability of high frequency data on the limit order book (see www.inetats. com) ensures a fair playing field where various agents can post limit orders at the prices they choose. In this paper, we study the optimal submission strategies of bid and ask orders in such a limit order book.

The pricing strategies of dealers have been studied extensively in the microstructure literature. The two most often addressed sources of risk facing the dealer are (i) the inventory risk arising from uncertainty in the asset's value

Of crucial importance to us will be the arrival rate of \*Corresponding author. Email: sashastoikov@gmail.com buy and sell orders that will reach our agent. In order

and (ii) the asymmetric information risk arising from informed traders. Useful surveys of their results can be found in Biais et al. (2004), Stoll (2003) and a book by O'Hara (1997). In this paper, we will focus on the inventory effect. In fact, our model is closely related to a paper by Ho and Stoll (1981), which analyses the optimal prices for a monopolistic dealer in a single stock. In their model, the authors specify a 'true' price for the asset, and derive optimal bid and ask quotes around this price, to account for the effect of the inventory. This inventory effect was found to be significant in an empirical study of AMEX Options by Ho and Macris (1984). In another paper by Ho and Stoll (1980), the problem of dealers under competition is analysed and the bid and ask prices are shown to be related to the reservation (or indifference) prices of the agents. In our framework, we will assume that our agent is but one player in the market and the 'true' price is given by the market mid-price.

to model these arrival rates, we will draw on recent results in econophysics. One of the important achievements of this literature has been to explain the statistical properties of the limit order book (see Bouchaud et al. 2002, Luckock 2003, Potters and Bouchaud 2003, Smith et al. 2003). The focus of these studies has been to reproduce the observed patterns in the markets by introducing 'zero intelligence' agents, rather than modelling optimal strategies of rational agents. One possible exception is the work of Luckock (2003), who defines a notion of optimal strategies, without resorting to utility functions. Though our objective is different to that of the econophysics literature, we will draw on their results to infer reasonable arrival rates of buy and sell orders. In particular, the results that will be most useful to us are the size distribution of market orders (Maslow and Mills 2001, Weber and Rosenow 2005, Gabaix et al. 2006) and the temporary price impact of market orders (Bouchaud et al. 2002, Weber and Rosenow 2005).

Our approach, therefore, is to combine the utility framework of the Ho and Stoll approach with the microstructure of actual limit order books as described in the econophysics literature. The main result is that the optimal bid and ask quotes are derived in an intuitive two-step procedure. First, the dealer computes a personal indifference valuation for the stock, given his current inventory. Second, he calibrates his bid and ask quotes to the limit order book, by considering the probability with which his quotes will be executed as a function of their distance from the mid-price. In the balancing act between the dealer's personal risk considerations and the market environment lies the essence of our solution.

The paper is organized as follows. In section 2, we describe the main building blocks for the model: the dynamics of the mid-market price, the agent's utility objective and the arrival rate of orders as a function of the distance to the mid-price. In section 3, we solve for the optimal bid and ask quotes, and relate them to the reservation price of the agent, given his current inventory. We then present an approximate solution, numerically simulate the performance of our agent's strategy and compare its Profit and Loss (P&L) profile to that of a benchmark strategy.

# 2. The model

# 2.1. The mid-price of the stock

For simplicity, we assume that money market pays no interest. The mid-market price, or mid-price, of the

stock evolves according to

$$dS_{u} = \sigma dW_{u} \tag{1}$$

with initial value  $S_t = s$ . Here  $W_t$  is a standard onedimensional Brownian motion and  $\sigma$  is constant.† Underlying this continuous-time model is the implicit assumption that our agent has no opinion on the drift or any autocorrelation structure for the stock.

This mid-price will be used solely to value the agent's assets at the end of the investment period. He may not trade costlessly at this price, but this source of randomness will allow us to measure the risk of his inventory in stock. In section 2.4 we will introduce the possibility to trade through limit orders.

### 2.2. The optimizing agent with finite horizon

The agent's objective is to maximize the expected exponential utility of his P&L profile at a terminal time *T*. This choice of convex risk measure is particularly convenient, since it will allow us to define reservation (or indifference) prices which are independent of the agent's wealth.

We first model an inactive trader who does not have any limit orders in the market and simply holds an inventory of q stocks until the terminal time T. This 'frozen inventory' strategy will later prove to be useful in the case when limit orders are allowed. The agent's value function is

$$v(x, s, q, t) = E_t[-\exp(-\gamma(x + qS_T))],$$

where *x* is the initial wealth in dollars. This value function can be written as

$$v(x, s, q, t) = -\exp(-\gamma x) \exp(-\gamma q s) \exp\left(\frac{\gamma^2 q^2 \sigma^2 (T - t)}{2}\right),$$
(3)

which shows us directly its dependence on the market parameters.

We may now define the reservation bid and ask prices for the agent. The reservation bid price is the price that would make the agent indifferent between his current portfolio and his current portfolio plus one stock. The reservation ask price is defined similarly below. We stress that this is a subjective valuation from the point of view of the agent and does not reflect a price at which trading should occur.

**Definition 1.** Let v be the value function of the agent. His reservation bid price  $r^b$  is given implicitly by the

†We choose this model over the standard geometric Brownian motion to ensure that the utility functionals introduced in the sequel remain bounded. In practical applications, we could also use a dimensionless model such as

$$\frac{\mathrm{d}S_u}{S_u} = \sigma \mathrm{d}W_u \tag{2}$$

with initial value  $S_t = s$ . To avoid mathematical infinities, exponential utility functions could be modified to a standard mean/variance objective with the same Taylor-series expansion. The essence of the results would remain. More details regarding the model (2) with mean/variance utility are given in the appendix.

relation

$$v(x - r^b(s, q, t), s, q + 1, t) = v(x, s, q, t).$$
 (4)

The reservation ask price  $r^a$  solves

$$v(x + r^a(s, q, t), s, q - 1, t) = v(x, s, q, t).$$
 (5)

A simple computation involving equations (3), (4) and (5) yields a closed-form expression for the two prices

$$r^{a}(s, q, t) = s + (1 - 2q)\frac{\gamma\sigma^{2}(T - t)}{2}$$
 (6)

and

$$r^{b}(s,q,t) = s + (-1 - 2q)\frac{\gamma \sigma^{2}(T-t)}{2}$$
 (7)

in the setting where no trading is allowed. We will refer to the average of these two prices as the *reservation* or *indifference* price

$$r(s, q, t) = s - q\gamma\sigma^{2}(T - t), \tag{8}$$

given that the agent is holding q stocks. This price is an adjustment to the mid-price, which accounts for the inventory held by the agent. If the agent is long stock (q>0), the reservation price is below the mid-price, indicating a desire to liquidate the inventory by selling stock. On the other hand, if the agent is short stock (q<0), the reservation price is above the mid-price, since the agent is willing to buy stock at a higher price.

## 2.3. The optimizing agent with infinite horizon

Because of our choice of a terminal time T at which we measure the performance of our agent, the reservation price (8) depends on the time interval (T-t). Intuitively, the closer our agent is to time T, the less risky his inventory in stock is, since it can be liquidated at the midprice  $S_T$ . In order to obtain a stationary version of the reservation price, we may consider an infinite horizon objective of the form

$$\bar{v}(x, s, q) = E \left[ \int_0^\infty -\exp(-\omega t) \exp(-\gamma (x + qS_t)) dt \right].$$

The stationary reservation prices (defined in the same way as in Definition 1) are given by

$$\bar{r}^{a}(s, q) = s + \frac{1}{\gamma} \ln \left( 1 + \frac{(1 - 2q)\gamma^{2}\sigma^{2}}{2\omega - \gamma^{2}q^{2}\sigma^{2}} \right)$$

and

$$\bar{r}^b(s, q) = s + \frac{1}{\gamma} \ln\left(1 + \frac{(-1 - 2q)\gamma^2 \sigma^2}{2\omega - \gamma^2 q^2 \sigma^2}\right),$$

where  $\omega > (1/2)\gamma^2\sigma^2q^2$ .

The parameter  $\omega$  may therefore be interpreted as an upper bound on the inventory position our agent is allowed to take. The natural choice of  $\omega = (1/2)\gamma^2\sigma^2(q_{\text{max}}+1)^2$  would ensure that the prices defined above are bounded.

#### 2.4. Limit orders

We now turn to an agent who can trade in the stock through limit orders that he sets around the mid-price given by (1). The agent quotes the bid price  $p^b$  and the ask price  $p^a$ , and is committed to respectively buy and sell one share of stock at these prices, should he be 'hit' or 'lifted' by a market order. These limit orders  $p^b$  and  $p^a$  can be continuously updated at no cost. The distances

$$\delta^b = s - p^b$$

and

$$\delta^a = p^a - s$$

and the current shape of the limit order book determine the priority of execution when large market orders get executed.

For example, when a large market order to buy Q stocks arrives, the Q limit orders with the lowest ask prices will automatically execute. This causes a temporary market impact, since transactions occur at a price that is higher than the mid-price. If  $p^Q$  is the price of the highest limit order executed in this trade, we define

$$\Delta p = p^Q - s$$

to be the temporary market impact of the trade of size Q. If our agent's limit order is within the range of this market order, i.e. if  $\delta^a < \Delta p$ , his limit order will be executed.

We assume that market buy orders will 'lift' our agent's sell limit orders at Poisson rate  $\lambda^a(\delta^a)$ , a decreasing function of  $\delta^a$ . Likewise, orders to sell stock will 'hit' the agent's buy limit order at Poisson rate  $\lambda^b(\delta^b)$ , a decreasing function of  $\delta^b$ . Intuitively, the further away from the midprice the agent positions his quotes, the less often he will receive buy and sell orders.

The wealth and inventory are now stochastic and depend on the arrival of market sell and buy orders. Indeed, the wealth in cash jumps every time there is a buy or sell order

$$dX_t = p^a dN_t^a - p^b dN_t^b$$

where  $N_t^b$  is the amount of stocks bought by the agent and  $N_t^a$  is the amount of stocks sold.  $N_t^b$  and  $N_t^a$  are Poisson processes with intensities  $\lambda^b$  and  $\lambda^a$ . The number of stocks held at time t is

$$q_t = N_t^b - N_t^a.$$

The objective of the agent who can set limit orders is

$$u(s, x, q, t) = \max_{sa} E_t[-\exp(-\gamma(X_T + q_T S_T))]$$

Notice that, unlike the setting described in the previous subsection, the agent controls the bid and ask prices and therefore indirectly influences the flow of orders he receives.

Before turning to the solution of this problem, we consider some realistic functional forms for the intensities  $\lambda^a(\delta^a)$  and  $\lambda^b(\delta^b)$  inspired by recent results in the econophysics literature.

### 2.5. The trading intensity

One of the main objectives of the econophysics community has been to describe the laws governing the microstructure of financial markets. Here, we will be focusing on the results which address the Poisson intensity  $\lambda$  with which a limit order will be executed as a function of its distance  $\delta$  to the mid-price. In order to quantify this, we need to know statistics on (i) the overall frequency of market orders, (ii) the distribution of their size and (iii) the temporary impact of a large market order. Aggregating these results suggests that  $\lambda$  should decay as an exponential or a power law function.

For simplicity, we assume a constant frequency  $\Lambda$  of market buy or sell orders. This could be estimated by dividing the total volume traded over a day by the average size of market orders on that day.

The distribution of the size of market orders has been found by several studies to obey a power law. In other words, the density of market order size is

$$f^{\mathcal{Q}}(x) \propto x^{-1-\alpha} \tag{9}$$

for large x, with  $\alpha = 1.53$  in Gopikrishnan *et al.* (2000) for US stocks,  $\alpha = 1.4$  in Maslow and Mills (2001) for shares on the NASDAQ and  $\alpha = 1.5$  in Gabaix *et al.* (2006) for the Paris Bourse.

There is less consensus on the statistics of the market impact in the econophysics literature. This is due to a general disagreement over how to define it and how to measure it. Some authors find that the change in price  $\Delta p$  following a market order of size Q is given by

$$\Delta n \propto Q^{\beta}$$
. (10)

where  $\beta = 0.5$  in Gabaix *et al.* (2006) and  $\beta = 0.76$  in Weber and Rosenow (2005). Potters and Bouchaud (2003) find a better fit to the function

$$\Delta p \propto \ln(Q)$$
. (11)

Aggregating this information, we may derive the Poisson intensity at which our agent's orders are executed. This intensity will depend only on the distance of his quotes to the mid-price, i.e.  $\lambda^b(\delta^b)$  for the arrival of sell orders and  $\lambda^a(\delta^a)$  for the arrival of buy orders. For instance, using (9) and (11), we derive

$$\lambda(\delta) = \Lambda P(\Delta p > \delta)$$

$$= \Lambda P(\ln(Q) > K\delta)$$

$$= \Lambda P(Q > \exp(K\delta))$$

$$= \Lambda \int_{\exp(K\delta)}^{\infty} x^{-1-\alpha} dx$$

$$= A \exp(-k\delta)$$
(12)

where  $A = \Lambda/\alpha$  and  $k = \alpha K$ . In the case of a power price impact (10), we obtain an intensity of the form

$$\lambda(\delta) = B\delta^{-\alpha/\beta}$$
.

Alternatively, since we are interested in short term liquidity, the market impact function could be derived directly by integrating the density of the limit order book. This procedure is described in Smith *et al.* (2003) and Weber and Rosenow (2005) and yields what is sometimes called the 'virtual' price impact.

#### 3. The solution

# 3.1. Optimal bid and ask quotes

Recall that our agent's objective is given by the value function

$$u(s, x, q, t) = \max_{s^a, s^b} E_t[-\exp(-\gamma (X_T + q_T S_T))]$$
 (13)

where the optimal feedback controls  $\delta^a$  and  $\delta^b$  will turn out to be time and state dependent. This type of optimal dealer problem was first studied by Ho and Stoll (1981). One of the key steps in their analysis is to use the dynamic programming principle to show that the function u solves the following Hamilton–Jacobi–Bellman equation

$$\begin{cases} u_t + \frac{1}{2}\sigma^2 u_{ss} + \max_{\delta^b} \lambda^b (\delta^b) [u(s, x - s + \delta^b, q + 1, t) \\ -u(s, x, q, t)] + \max_{\delta^a} \lambda^a (\delta^a) [u(s, x + s + \delta^a, q - 1, t) \\ -u(s, x, q, t)] = 0, \\ u(s, x, q, T) = -\exp(-\gamma (x + qs)). \end{cases}$$

The solution to this nonlinear PDE is continuous in the variables s, x and t and depends on the discrete values of the inventory q. Due to our choice of exponential utility, we are able to simplify the problem with the ansatz

$$u(s, x, q, t) = -\exp(-\gamma x)\exp(-\gamma \theta(s, q, t)). \tag{14}$$

Direct substitution yields the following equation for  $\theta$ :

$$\begin{cases} \theta_{t} + (1/2)\sigma^{2}\theta_{ss} - (1/2)\sigma^{2}\gamma\theta_{s}^{2} \\ + \max_{\delta^{b}} \left[ \frac{\lambda^{b}(\delta^{b})}{\gamma} [1 - e^{\gamma(s - \delta^{b} - r^{b})}] \right] \\ + \max_{\delta^{b}} \left[ \frac{\lambda^{a}(\delta^{a})}{\gamma} [1 - e^{-\gamma(s + \delta^{a} - r^{a})}] \right] = 0, \end{cases}$$

$$\theta(s, q, T) = qs.$$

$$(15)$$

Applying the definition of reservation bid and ask prices (given in section 2.2) to the ansatz (14), we find that  $r^b$  and  $r^a$  depend directly on this function  $\theta$ . Indeed,

$$r^{b}(s, q, t) = \theta(s, q + 1, t) - \theta(s, q, t)$$
 (16)

is the reservation bid price of the stock, when the inventory is q and

$$r^{a}(s, q, t) = \theta(s, q, t) - \theta(s, q - 1, t)$$
 (17)

is the reservation ask price, when the inventory is q. From the first-order optimality condition in (15),

we obtain the optimal distances  $\delta^b$  and  $\delta^a$ . They are given by the implicit relations

$$s - r^{b}(s, q, t) = \delta^{b} - \frac{1}{\gamma} \ln \left( 1 - \gamma \frac{\lambda^{b}(\delta^{b})}{(\partial \lambda^{b} / \partial \delta)(\delta^{b})} \right)$$
(18)

and

$$r^{a}(s, q, t) - s = \delta^{a} - \frac{1}{\gamma} \ln\left(1 - \gamma \frac{\lambda^{a}(\delta^{a})}{(\partial \lambda^{a}/\partial \delta)(\delta^{a})}\right). \tag{19}$$

In summary, the optimal bid and ask quotes are obtained through an intuitive, two-step procedure. First, we solve the PDE (15) in order to obtain the reservation bid and ask prices  $r^b(s,q,t)$  and  $r^a(s,q,t)$ . Second, we solve the implicit equations (18) and (19) and obtain the optimal distances  $\delta^b(s,q,t)$  and  $\delta^a(s,q,t)$  between the mid-price and optimal bid and ask quotes. This second step can be interpreted as a calibration of our indifference prices to the current market supply  $\lambda^b$  and demand  $\lambda^a$ .

#### 3.2. Asymptotic expansion in q

The main computational difficulty lies in solving equation (15). The order arrival terms (i.e. the terms to be maximized in the expression) are highly nonlinear and may depend on the inventory. We therefore suggest an asymptotic expansion of  $\theta$  in the inventory variable q, and a linear approximation of the order arrival terms. In the case of symmetric, exponential arrival rates

$$\lambda^{a}(\delta) = \lambda^{b}(\delta) = Ae^{-k\delta}, \tag{20}$$

the indifference prices  $r^a(s, q, t)$  and  $r^b(s, q, t)$  coincide with their 'frozen inventory' values, as described in section 2.2.

Substituting the optimal values given by equations (18) and (19) into (15) and using the exponential arrival rates, we obtain

$$\begin{cases} \theta_t + \frac{1}{2}\sigma^2\theta_{ss} - \frac{1}{2}\sigma^2\gamma\theta_s^2 + \frac{A}{k+\gamma}(e^{-k\delta^a} + e^{-k\delta^b}) = 0, \\ \theta(s, q, T) = qs. \end{cases}$$
(21)

Consider an asymptotic expansion in the inventory variable

$$\theta(q, s, t) = \theta^{0}(s, t) + q\theta^{1}(s, t) + \frac{1}{2}q^{2}\theta^{2}(s, t) + \cdots$$
 (22)

The exact relations for the indifference bid and ask prices, (16) and (17), yield

$$r^b(s, q, t) = \theta^1(s, t) + (1 + 2q)\theta^2(s, t) + \cdots$$
 (23)

and

$$r^{a}(s, q, t) = \theta^{1}(s, t) + (-1 + 2q)\theta^{2}(s, t) + \cdots$$
 (24)

Using equations (24) and (23), along with the optimality conditions (18) and (19), we find that the optimal pricing strategy amounts to quoting a spread of

$$\delta^a + \delta^b = -2\theta^2(s, t) + \frac{2}{\gamma} \ln\left(1 + \frac{\gamma}{k}\right) \tag{25}$$

around the reservation price given by

$$r(s, q, t) = \frac{r^a + r^b}{2} = \theta^1(s, t) + 2q\theta^2(s, t).$$

The term  $\theta^1$  can be interpreted as the reservation price, when the inventory is zero. The term  $\theta^2$  may be interpreted as the sensitivity of the market maker's quotes to changes in inventory. For instance, since  $\theta^2$  will turn out to be negative, accumulating a long position q > 0 will result in aggressively low quotes.

The bid-ask spread in (25) is independent of the inventory. This follows from our assumption of exponential arrival rates. The spread consists of two components, one that depends on the sensitivity to changes in inventory  $\theta^2$  and one that depends on the intensity of arrival of orders, through the parameter k.

Taking a first-order approximation of the order arrival term

$$\frac{A}{k+\gamma}(e^{-k\delta^a} + e^{-k\delta^b}) = \frac{A}{k+\gamma}(2 - k(\delta^a + \delta^b) + \cdots), \quad (26)$$

we notice that the linear term does not depend on the inventory q. Therefore, if we substitute (22) and (26) into (21) and group terms of order q, we obtain

$$\begin{cases} \theta_t^1 + \frac{1}{2}\sigma^2\theta_{ss}^1 = 0, \\ \theta^1(s, T) = s, \end{cases}$$
 (27)

whose solution is  $\theta^1(s, t) = s$ . Grouping terms of order  $q^2$  yields

$$\begin{cases} \theta_t^2 + \frac{1}{2}\sigma^2\theta_{ss}^2 - \frac{1}{2}\sigma^2\gamma(\theta_s^1)^2 = 0\\ \theta^2(s, T) = 0. \end{cases}$$
 (28)

whose solution is  $\theta^2 = -(1/2)\sigma^2\gamma(T-t)$ . Thus, for this linear approximation of the order arrival term, we obtain the same indifference price

$$r(s,t) = s - q\gamma\sigma^2(T-t)$$
 (29)

as for the 'frozen inventory' problem from section 2.2. We then set a bid/ask spread given by

$$\delta^{a} + \delta^{b} = \gamma \sigma^{2} (T - t) + \frac{2}{\gamma} \ln \left( 1 + \frac{\gamma}{k} \right)$$
 (30)

around this indifference or reservation price. Note that if we had taken a quadratic approximation of the order arrival term, we would still obtain  $\theta^1 = s$ , but the sensitivity term  $\theta^2(s, t)$  would solve a nonlinear PDE.

Equations (29) and (30) thus provide us with simple expressions for the bid and ask prices in terms of our model parameters. This approximate solution

also simplifies the simulations we perform in the next

#### 3.3. Numerical simulations

We now test the performance of our strategy, focusing primarily on the shape of the P&L profile and the final inventory  $q_T$ . We will refer to our strategy as the 'inventory' strategy, and compare it to a benchmark strategy that is symmetric around the mid-price, regardless of the inventory. This strategy, which we refer to as the 'symmetric' strategy, uses the average spread of the inventory strategy, but centres it around the mid-price, rather than the reservation price.

In practice, the choice of time step dt is a subtle one. On the one hand, dt must be small enough so that the probability of multiple orders reaching our agent is small. On the other hand, dt must be larger than the typical tick time, otherwise the agent's quotes will be updated so frequently that he will not see any orders (particularly if his quotes are outside the market bid/ask spread).

As far as our simulation is concerned, we chose the following parameters: s=100, T=1,  $\sigma=2$ , dt=0.005, q=0,  $\gamma=0.1$ , k=1.5 and A=140. The simulation is obtained through the following procedure: at time T, the agent's quotes  $\delta^a$  and  $\delta^b$  are computed, given the state variables. At time t+dt, the state variables are updated. With probability  $\lambda^a(\delta^a)dt$ , the inventory variable decreases by one and the wealth increases by  $s+\delta^a$ . With probability  $\lambda^b(\delta^b)dt$ , the inventory increases by one and the wealth decreases by  $s-\delta^b$ . The mid-price is updated by a random increment  $\pm \sigma \sqrt{dt}$ . Figure 1 illustrates the bid and ask quotes for one simulation of a stock path.

Notice that, at time t = 0.15, the bid and ask quotes are relatively high, indicating that the inventory position must be negative (or short stock). Since the bid price is aggressively placed near the mid-price, our agent is more likely to buy stock and the inventory quickly returns to zero by time t = 0.2. As we approach the terminal time, our agent's bid/ask quotes look more like a strategy that is symmetric around the mid-price. Indeed, when we are close to the terminal time, our inventory position is considered less risky, since the mid-price is less likely to move drastically.

We then run 1000 simulations to compare our 'inventory' strategy to the 'symmetric' strategy. This strategy uses the average bid/ask spread of the inventory strategy over the time period, but centres it around the mid-price. For example, the performance of the symmetric strategy that quotes a bid/ask spread of \$1.49 (corresponding to the average spread of the optimal agent with  $\gamma = 0.1$ ) is displayed in table 1. This symmetric strategy has a higher return and higher standard deviation than the inventory strategy. The symmetric strategy obtains a slightly higher return since it is centred around the mid-price, and therefore receives a higher

![](_page_5_Figure_9.jpeg)

Figure 1. The mid-price and the optimal bid and ask quotes.

Table 1. 1000 simulations with  $\gamma = 0.1$ .

| Strategy  | Average spread | Profit | Std<br>(Profit) | Final q | Std<br>(Final q) |
|-----------|----------------|--------|-----------------|---------|------------------|
| Inventory | 1.49           | 65.0   | 6.6             | 0.08    | 2.9              |
| Symmetric | 1.49           | 68.4   | 12.7            | 0.26    | 8.4              |

![](_page_5_Figure_13.jpeg)

Figure 2.  $\gamma = 0.1$ .

Table 2. 1000 simulations with  $\gamma = 0.01$ .

| Strategy  | Average<br>Spread | Profit | Std<br>(Profit) | Final q | Std<br>(Final q) |
|-----------|-------------------|--------|-----------------|---------|------------------|
| Inventory | 1.35              | 68.6   | 8.7             | 0.12    | 5.1              |
| Symmetric | 1.35              | 68.8   | 12.8            | 0.09    | 8.7              |

volume of orders than the inventory strategy. However, the inventory strategy obtains a P&L profile with a much smaller variance, as illustrated in the histogram in figure 2.

![](_page_6_Figure_2.jpeg)

Figure 3.  $\gamma = 0.01$ .

Table 3. 1000 simulations with  $\gamma = 1$ .

| Strategy  | Average spread | Profit | Std<br>(Profit) | Final q | Std<br>(Final q) |
|-----------|----------------|--------|-----------------|---------|------------------|
| Inventory | 3.02           | 31.4   | 5.0             | 0.02    | 1.7              |
| Symmetric | 3.02           | 44.0   | 11.0            | 0.00    | 5.1              |

![](_page_6_Figure_6.jpeg)

Figure 4.  $\gamma = 1$ .

The results of the simulations comparing the 'inventory' strategy for  $\gamma = 0.01$  with the corresponding 'symmetric' strategy are displayed in table 2. This small value for  $\gamma$  represents an investor who is close to risk neutral. The inventory effect is therefore much smaller and the P&L profiles of the two strategies are very similar, as illustrated in figure 3. In fact, in the limit as  $\gamma \to 0$  the two strategies are identical.

Finally, we display the performance of the two strategies for  $\gamma = 1$  in table 3. This choice corresponds to a very risk averse investor, who will go to great lengths

to avoid accumulating an inventory. This strategy produces low standard deviations of profits and final inventory, but generates more modest profits than the corresponding symmetric strategy (see figure 4).

#### References

Biais, B., Glosten, L. and Spatt, C., Market microstructure: a server of microfoundations, empirical results and policy implications. *J. Financ. Markets*, 2005, **8**, 217–264.

Bouchaud, J.-P., Mezard, M. and Potters, M., Statistical properties of stock order books: empirical results and models. *Quant. Finance*, 2002, **2**, 251–256.

Gabaix, X., Gopikrishnan, P., Plerou, V. and Stanley, H.E., Institutional investors and stock market volatility. *Quart. J. Econ.*, 2006, 121, 461–504.

Gopikrishnan, P., Plerou, V., Gabaix, X. and Stanley, H., Statistical properties of share volume traded in financial markets. *Phys. Rev. E*, 2000, **62**, R4493–R4496.

Ho, T. and Macris, R., Dealer bid–ask quotes and transaction prices: an empirical study of some AMEX options. *J. Finance*, 1984, **39**, 23–45.

Ho, T. and Stoll, H., On dealer markets under competition. *J. Finance*, 1980, **35**, 259–267.

Ho, T. and Stoll, H., Optimal dealer pricing under transactions and return uncertainty. *J. Financ. Econ.*, 1981, **9**, 47–73.

Luckock, H., A steady-state model of the continuous double auction. Quant. Finance, 2003, 3, 385–404.

Maslow, S. and Mills, M., Price fluctuations from the order book perspective: empirical facts and a simple model. *Phys. A*, 2001, **299**, 234–246.

O'Hara, M., *Market Microstructure Theory*, 1997 (Blackwell: Cambridge).

Potters, M. and Bouchaud, J.-P., More statistical properties of order books and price impact. *Physica A: Stat. Mech. Appl.*, 2003, 324, 133–140.

Smith, E., Farmer, J.D., Gillemot, L. and Krishnamurthy, S., Statistical theory of the continuous double auction. *Quant. Finance*, 2003, **3**, 481–514.

Stoll, H.R., Market microstructure. In *Handbook of the Economics of Finance*, edited by G.M. Constantinides, *et al.*, 2003 (North Holland: Amsterdam).

Weber, P. and Rosenow, B., Order book approach to price impact. *Quant. Finance*, 2005, **5**, 357–364.

# **Appendix**

Herein, we consider the geometric Brownian motion

$$\frac{\mathrm{d}S_u}{S_u} = \sigma \mathrm{d}W_u$$

with initial value  $S_t = s$ , and the mean/variance objective

$$V(x, s, q, t) = E_t \left[ (x + qS_T) - \frac{\gamma}{2} (qS_T - qs)^2 \right],$$

where *x* is the initial wealth in dollars. This value function can be written as

$$V(x, s, q, t) = x + qs - \frac{\gamma q^2 s^2}{2} \left( e^{\sigma^2 (T - t)} - 1 \right).$$

This yields reservation prices of the form

$$R^{a}(s, q, t) = s + \frac{(1 - 2q)}{2} \gamma s^{2} \left( e^{\sigma^{2}(T - t)} - 1 \right)$$

and

$$R^{b}(s, q, t) = s + \frac{(-1 - 2q)}{2} \gamma s^{2} \left( e^{\sigma^{2}(T - t)} - 1 \right).$$

These results are analogous to the ones obtained in section 2.2.