# UrbanCart Retention EDA — Problem Definition

## 1) Business Context
UrbanCart is a US-based online delivery platform connecting customers with local vendors (restaurants, grocery stores, pharmacies, and retail). It operates in major US cities and offers on-demand, scheduled, and express delivery. The last‑mile delivery market is highly competitive, making customer retention a critical business priority. Retaining existing customers is generally more cost-effective than acquiring new ones, and higher retention improves customer lifetime value (CLV), profitability, and long-term unit economics. UrbanCart needs to understand which customer, service, and experience factors are most closely associated with repeat engagement.

## 2) Project Objective
Perform Exploratory Data Analysis (EDA) and basic hypothesis testing to identify the main factors that influence customer retention at UrbanCart. The analysis will determine which operational, behavioral, and experience variables are linked to continued customer activity and repeat usage, and will generate actionable insights to support retention-focused business decisions.

## 3) Key Performance Indicators (KPIs)
The project will track the following retention-focused KPIs (overall and segmented by city, service type, and customer tenure where applicable):

1. **30‑Day Retention Rate (Primary)**
   - **Definition:** % of customers who place at least one additional order within 30 days after an index date (e.g., first order date or cohort start).
   - **Formula:** `(# customers with ≥1 order in days 1–30 after index) / (# customers in cohort)`
   - **Direction:** Higher is better.

2. **90‑Day Retention Rate**
   - **Definition:** % of customers who place at least one additional order within 90 days after the index date.
   - **Formula:** `(# customers with ≥1 order in days 1–90 after index) / (# customers in cohort)`
   - **Direction:** Higher is better.

3. **Repeat Order Frequency (First 90 Days)**
   - **Definition:** Average number of orders per customer in the first 90 days after the index date (can be computed for all customers and/or only retained customers).
   - **Formula:** `(Total orders in days 1–90 after index) / (# customers in cohort)`
   - **Direction:** Higher is better.

## 4) Key Hypotheses to Test
Each hypothesis will be evaluated with exploratory comparisons (segment-level retention curves) and basic statistical tests (e.g., chi-square for categorical, Mann–Whitney/t-test for numeric), with effect sizes and confidence intervals where feasible.

1. **Delivery Reliability Drives Retention**
   - Customers experiencing higher on-time delivery performance (lower lateness vs ETA) have higher 30/90‑day retention and higher repeat order frequency.
   - **Candidate features:** on-time rate, median lateness minutes, % significantly late deliveries.

2. **Service Failures Reduce Retention**
   - Customers who experience cancellations, refunds, missing/incorrect items, substitutions (grocery), or support contacts are less likely to be retained.
   - **Candidate features:** cancellation rate, refund incidence, support tickets per order, issue flags.

3. **Early Engagement Predicts Longer-Term Retention**
   - Customers who place multiple orders early in their lifecycle (e.g., ≥2 orders in the first 14 days) are more likely to be retained at 30/90 days and show higher repeat order frequency.
   - **Candidate features:** orders in first 7/14 days, days-to-second-order, vendor/category diversity early on.

