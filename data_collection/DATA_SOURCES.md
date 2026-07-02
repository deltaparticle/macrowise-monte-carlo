# Manual Data Download Instructions

This file lists all the URLs from which the data collection scripts will
attempt to download data. If the automated scripts are blocked by rate
limits or IP restrictions, use these links to download data manually.

## 1. NSE India Indices

### NSE Historical Indices (Manual Download)
- **NSE Indices CSV**: https://www.nseindia.com/api/historical/indices/historical?symbol=NIFTY%2050&from=2000-01-01&to=2026-06-30
- **Nifty 50 Historical**: https://www.nseindia.com/content/indices/historical/Nifty%2050%20Data.csv
- **Nifty Bank Historical**: https://www.nseindia.com/content/indices/historical/Nifty%20Bank%20Data.csv
- **All NSE Indices**: https://www.nseindia.com/api/allIndices
- **NSE Data Download Page**: https://www.nseindia.com/get-quotes/equity?symbol=NIFTY%2050

### NSE Indices with Yahoo Finance Fallback
- Nifty 50: `^NSEI`
- Nifty Bank: `^NSEBANK`
- Nifty IT: `^CNXIT`
- Nifty Pharma: `^CNXPHARMA`
- Nifty FMCG: `^CNXFMCG`
- Nifty Auto: `^CNXAUTO`
- Nifty Realty: `^CNXREALTY`
- Nifty Financial Services: `NIFTY_FIN_SERVICE.NS`
- Nifty Midcap 100: `^CRSMID`
- Nifty Smallcap 100: `^CRSML`

### NSE G-Sec Indices
- Nifty 10Y G-Sec: https://www.nseindia.com/api/historical/indices/historical?symbol=NIFTY%2010%20YR%20G-SEC%20INDEX
- G-Sec Indices Page: https://www.niftyindices.com/

### BSE Indices
- Sensex Yahoo: `^BSESN`
- BSE Midcap: `BSE-MIDCAP.NS`
- BSE Smallcap: `BSE-SMLCAP.NS`
- BSE 500: `BSE-500.NS`

## 2. RBI Data

### RBI Weekly Statistical Supplement (WSS)
- **WSS Home**: https://www.rbi.org.in/Scripts/WS_SectionIndex.aspx
- **Table H1 - Bank Rate**: https://www.rbi.org.in/scripts/WSSViewDetail.aspx?TABLE=H1&TYPE=0
- **Table H2 - CRR/SLR/MSF**: https://www.rbi.org.in/scripts/WSSViewDetail.aspx?TABLE=H2&TYPE=0
- **Table H3 - G-Sec Yields**: https://www.rbi.org.in/scripts/WSSViewDetail.aspx?TABLE=H3&TYPE=0
- **Table H8 - 91D T-Bill**: https://www.rbi.org.in/scripts/WSSViewDetail.aspx?TABLE=H8&TYPE=0
- **Table H9 - 182D T-Bill**: https://www.rbi.org.in/scripts/WSSViewDetail.aspx?TABLE=H9&TYPE=0
- **Table H10 - 364D T-Bill**: https://www.rbi.org.in/scripts/WSSViewDetail.aspx?TABLE=H10&TYPE=0
- **Table H12 - CPI Rural**: https://www.rbi.org.in/scripts/WSSViewDetail.aspx?TABLE=H12&TYPE=0
- **Table H13 - CPI Urban**: https://www.rbi.org.in/scripts/WSSViewDetail.aspx?TABLE=H13&TYPE=0
- **Table H14 - CPI Combined**: https://www.rbi.org.in/scripts/WSSViewDetail.aspx?TABLE=H14&TYPE=0
- **Table H15 - FX Reference**: https://www.rbi.org.in/scripts/WSSViewDetail.aspx?TABLE=H15&TYPE=0
- **Table H16 - Gold & Silver**: https://www.rbi.org.in/scripts/WSSViewDetail.aspx?TABLE=H16&TYPE=0

### RBI Database on Indian Economy (DBIE)
- **DBIE Home**: https://data.rbi.org.in/
- **DBIE Search**: https://data.rbi.org.in/app
- **RBI Data Downloads**: https://www.rbi.org.in/Scripts/Statistics.aspx

### RBI Press Releases
- **MPR Press Releases**: https://www.rbi.org.in/Scripts/MPRDisplay.aspx
- **Policy Rate History**: https://www.rbi.org.in/Scripts/PressReleaseDisplay.aspx

## 3. CPI / Inflation Data

### Official Indian Sources
- **MOSPI CPI**: https://www.mospi.gov.in/sites/default/files/statistical_data/cpi_inflation_data.csv
- **MOSPI National Accounts**: https://www.mospi.gov.in/
- **RBI WSS H14 (Combined CPI)**: https://www.rbi.org.in/scripts/WSSViewDetail.aspx?TABLE=H14&TYPE=0
- **CSO CPI**: https://cso.gov.in/

### International Sources (Backup)
- **FRED - India CPI**: https://fred.stlouisfed.org/series/INDCPIALLMINMEI (via pandas-datareader)
- **World Bank India CPI**: https://data.worldbank.org/indicator/FP.CPI.TOTL.ZG?locations=IN

## 4. USD / INR Exchange Rates

### RBI Reference Rate
- **RBI WSS H15**: https://www.rbi.org.in/scripts/WSSViewDetail.aspx?TABLE=H15&TYPE=0

### Market Rates
- **Yahoo Finance**: `USDINR=X`
- **RBI Historical Rates**: https://data.rbi.org.in (search for "USD/INR")

## 5. Gold & Silver Prices

### MCX (Multi Commodity Exchange)
- **MCX Historical Data**: https://www.mcxindia.com/
- **Gold on MCX (Yahoo)**: `GOLDBEES.NS` (GoldBeES ETF)
- **Silver on MCX (Yahoo)**: `SILVERBEES.NS` (SilverBeES ETF)

### RBI WSS H16
- https://www.rbi.org.in/scripts/WSSViewDetail.aspx?TABLE=H16&TYPE=0

## 6. AMFI Mutual Fund NAV

### AMFI India
- **NAV History Report**: https://www.amfiindia.com/spages/NAVHistoryReport.aspx
- **All NAV Report**: https://www.amfiindia.com/spages/NAVAllReport.aspx
- **Scheme Master List**: https://www.amfiindia.com/spages/SchemeMaster.aspx
- **Scheme Search**: https://www.amfiindia.com/Design_scheme_search.aspx
- **AMFI NAV Download Page**: https://www.amfiindia.com/nav-history-download

### MFAPI.in (Alternative)
- **MFAPI.in**: https://api.mfapi.in/
- **MFAPI GitHub**: https://github.com/narayanmk/mfapi-py

### Value Research Online
- **VRO**: https://www.valueresearchonline.com/funds/

## 7. Indian Tax Rules

### Official Sources
- **Income Tax Act**: https://incometaxindia.gov.in/pages/acts/income-tax-act.aspx
- **Income Tax India Portal**: https://www.incometaxindia.gov.in/
- **Budget 2024**: https://www.indiabudget.gov.in/
- **Finance Act 2024**: https://www.indiabudget.gov.in/doc/bill/foa.pdf
- **CBDT Notifications**: https://incometaxindia.gov.in/pages/circulars-index.aspx

### Key Tax Changes (FY 2024-25)
- New tax regime is default (July 2024 Budget)
- Standard deduction: Rs. 75,000 (new regime)
- Rebate u/s 87A: Up to Rs. 7 lakh income (new regime)
- LTCG on equity: 10% above Rs. 1.25 lakh per FY
- STCG on equity: 15%
- Debt LTCG: 10% without indexation, 20% with indexation (hold > 3 yrs)
- ELSS: 3-year lock-in, LTCG same as equity

### Tax Deduction Limits
- **Section 80C**: Rs. 1,50,000 (PF, PPF, ELSS, LIC, Home Loan Principal)
- **Section 80CCD(1B)**: Rs. 50,000 (additional NPS)
- **Section 80CCD(2)**: Unlimited (employer NPS contribution)
- **Section 24(b)**: Rs. 2,00,000 (home loan interest, self-occupied)
- **Section 80EEA**: Rs. 1,50,000 (extra home loan interest for new home)
- **Section 80D**: Rs. 25,000 self+family, Rs. 50,000 parents (senior citizens)
- **Section 80G**: 50% or 100% of donation (based on org)

### NPS Taxation
- 60% of corpus tax-free at withdrawal
- 40% must be used for annuity purchase (tax-free)
- Remaining 40% if withdrawn as lump sum is taxable

## 8. Life Expectancy Data

### Indian Sources
- **SRS Life Tables (2016-20)**: https://censusindia.gov.in/nada/index.php/catalog/42732
- **SRS 2012-16**: https://censusindia.gov.in/nada/index.php/catalog/35594
- **SRS 2010-14**: https://censusindia.gov.in/nada/index.php/catalog/32091
- **World Bank Life Expectancy India**: https://data.worldbank.org/indicator/SP.DYN.LE00.IN?locations=IN
- **UN World Population Prospects**: https://population.un.org/wpp/

### Recommended Life Tables
- **Period Life Table**: https://www.rdplf.in/Indian-Life-Table.pdf
- **IAP Life Tables**: Indian Academy of Pediatrics
- **Sample Registration System (SRS)**: https://censusindia.gov.in/nada/index.php/catalog/RIAM

## 9. PortfolioVisualizer Reference

For methodology reference on the original tool:
- **Monte Carlo**: https://www.portfoliovisualizer.com/monte-carlo-simulation
- **FAQ/Documentation**: https://www.portfoliovisualizer.com/faq
- **Methodology**: https://www.portfoliovisualizer.com/faq#methodology
