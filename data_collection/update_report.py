# Update data_collection.md with corrected final statistics
import re

with open('data_collection/data_collection.md', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix summary stats table
content = content.replace(
    '| **Total unique asset price series** | **198** (up from 121) |',
    '| **Total unique asset price series** | **134** (clean final) |'
)
content = content.replace(
    '| **Total assets with statistics** | **197** |',
    '| **Total assets with statistics** | **133** |'
)
content = content.replace(
    'We have:\n- **198 asset classes**',
    'We have:\n- **134 asset classes**'
)
content = content.replace(
    '| Historical return sequences | Have 317 months, 121 assets |',
    '| Historical return sequences | Have 317 months, **134 assets** |'
)

# Fix G-Sec synthetic entries in asset table
old_gsec = '| **G-Sec Bond 10Y (Synthetic)** | GSEC_10Y_TRI | 14.3 | 6.36% | 4.28% | -0.03 | ~-10% | From FRED yields; captures interest rate risk |\n| **G-Sec Bond 5Y (Synthetic)** | GSEC_5Y_TRI | 14.3 | 6.25% | 2.48% | — | ~-5% | Lower duration, lower vol vs 10Y |'
new_gsec = '| **G-Sec Bond Proxy** | SBI Gilt Fund | 13.4 | 8.90% | 4.07% | 0.59 | -5.17% | Real gilt fund; captures interest rate risk |\n| **Corporate Bond Proxy** | HDFC Corp Bond | 13.4 | 7.99% | 2.07% | 0.72 | -2.46% | Low vol debt (actual NAVs) |'
content = content.replace(old_gsec, new_gsec)

# Add note about synthetic G-Sec removal
content = content.replace(
    '### The Honest Truth\n\nA faithful replica is limited by **India\'s data availability ceiling**',
    '### The Honest Truth\n\n**IMPORTANT CORRECTION:** Our synthetic G-SEC TRI (GAP-1) was found to be **6.32% vs 0.81% actual return** and **7x too volatile**. It has been **REMOVED**. We now use **real gilt fund NAVs** (SBI Gilt 8.90%, ICICI 8.57%, HDFC 7.52%, UTI 5.81%) that properly capture Indian bond returns with realistic volatility.\n\nA faithful replica is limited by **India\'s data availability ceiling**'
)

# Remove synthetic G-Sec from "what makes faithful" list
content = content.replace(
    '- We have **synthetic G-Sec TRI** from FRED yields for bond risk modeling\n',
    ''
)

# Fix the final data section
content = content.replace(
    '| Total raw data files | 11 source + 8 gap-fix + 6 derived v1 + 6 derived v2 + 6 derived final |',
    '| Total raw data files | 11 source + 8 gap-fix + 6 derived v1 + 6 derived v2 + 6 derived final |'
)
content = content.replace(
    '| G-Sec Bond TRI observations | 172 monthly (synthetic, 2012-2026) |',
    '| **Real gilt funds as proxy** | 14 clean bond/gilt funds (SBI Gilt 8.90%, HDFC Corp 7.99%, etc.) |'
)
content = content.replace(
    '| Clean liquid fund NAVs | 9 (SBI, Nippon, UTI - HDFC & Kotak excluded) |',
    '| **Clean liquid fund NAVs** | 6 (SBI Liquid x4, UTI Liquid - IDCW plans excluded) |'
)

# Fix Part 5 summary stats
content = content.replace(
    '| Total unique asset price series | **198** (up from 121) |\n| **Total assets with statistics** | **197** |\n| Total raw daily price rows | 8,134 |',
    '| Total unique asset price series | **134** (clean final - synthetic G-SEC removed) |\n| **Total assets with statistics** | **133** |\n| Total raw daily price rows | 8,108 |'
)
content = content.replace(
    '| Correlation matrix dimensions | **198 x 198** |',
    '| Correlation matrix dimensions | **134 x 134** |'
)
content = content.replace(
    '| Covariance matrix dimensions | **198 x 198** |',
    '| Covariance matrix dimensions | **134 x 134** |'
)

# Fix Part 4.5 Gap 1 summary
content = content.replace(
    '| **GAP-1** | No Indian G-Sec Bond TRI | **FIXED** - Synthetic G-Sec TRI constructed from FRED India 10Y yield',
    '| **GAP-1** | No Indian G-Sec Bond TRI | **REMOVED** - Synthetic G-Sec TRI was 6.32% vs 0.81% actual, 7x too volatile. **FIXED**: Now using real gilt fund NAVs (SBI/ICICI/HDFC/UTI Gilt Funds)'
)

# Update gap 1 detail text
content = content.replace(
    '### Gap Fix Results\n\n| # | Gap Description | Fix Applied | Status |',
    '### Gap Fix Results\n\n| # | Gap Description | Fix Applied | Status |\n| **GAP-1** | No Indian G-Sec Bond TRI | **REMOVED** - Synthetic was 6.32% vs 0.81% actual (7x too volatile). **FIXED** with real SBI/ICICI/HDFC/UTI gilt fund NAVs. See Gap Fix Details below. | FIXED |'
)

# Fix the "FIXED (Synthetic from FRED yields)" entry in the gap fix summary table
content = content.replace(
    "1. G-Sec Bond TRI:    FIXED (Synthetic from FRED yields)",
    "1. G-Sec Bond TRI:    REMOVED - was 7x too volatile. REPLACED with real gilt fund NAVs"
)

# Fix header stats
content = content.replace(
    '**Final Asset Count:** 198 unique price series, 197 with full statistics',
    '**Final Asset Count:** 134 unique price series, 133 with full statistics'
)

# Fix files table
content = content.replace(
    '| `all_prices_final.pkl` | 8,134 | 198 | Final combined prices (all gap fixes applied) |',
    '| `all_prices_final.pkl` | 8,108 | 134 | Final combined prices (no synthetic G-Sec, no corrupt MFs) |'
)
content = content.replace(
    '| `all_monthly_returns_final.pkl` | 317 | 198 | Monthly % returns (v2 final) |',
    '| `all_monthly_returns_final.pkl` | 317 | 134 | Monthly % returns (v2 final) |'
)
content = content.replace(
    '| `all_annual_returns_final.pkl` | 27 | 198 | Calendar-year returns (v2 final) |',
    '| `all_annual_returns_final.pkl` | 27 | 134 | Calendar-year returns (v2 final) |'
)
content = content.replace(
    '| `all_asset_statistics_final.pkl` | 197 | 13 | 13 metrics per asset (v2 final) |',
    '| `all_asset_statistics_final.pkl` | 133 | 13 | 13 metrics per asset (v2 final) |'
)
content = content.replace(
    '| `all_correlation_matrix_final.pkl` | 198 | 198 | Pairwise Pearson correlation (v2 final) |',
    '| `all_correlation_matrix_final.pkl` | 134 | 134 | Pairwise Pearson correlation (v2 final) |'
)
content = content.replace(
    '| `all_covariance_matrix_final.pkl` | 198 | 198 | Annualized covariance matrix (v2 final) |',
    '| `all_covariance_matrix_final.pkl` | 134 | 134 | Annualized covariance matrix (v2 final) |'
)

# Add GAP-1 detail section
old_gap1_section = '### Gap Fix Results'
new_gap1_section = '''### GAP-1 Detail: G-Sec Bond TRI — REMOVED

**What we tried:** Synthetic G-Sec TRI built from FRED India 10Y yield (INDIRLTLT01STM) using bond pricing model (6% coupon, ~8yr modified duration). Resulted in 6.36% annual return and 4.28% std dev.

**Why it failed:** When validated against actual SBI Gilt Fund NAVs over 161 common months:

| Metric | Synthetic G-Sec | SBI Gilt (Actual) | Difference |
|--------|---------------|------------------|------------|
| Annual return | 6.32% | 0.81% | +5.51pp (681% overestimate) |
| Annual volatility | 4.32% | 0.66% | 7x too high |
| Positive months | 70% | 47% | Directionally wrong |

**Root cause:** Our synthetic model uses a single 10Y bond with 8yr duration. Real gilt funds use duration-managed portfolios of ~2-3yr effective duration. We were 7x too volatile.

**Fix applied:** REPLACED with real gilt fund NAVs (SBI Gilt 8.90%, ICICI 8.57%, HDFC 7.52%, UTI 5.81%) — all clean, all within realistic ranges.

### Gap Fix Results'''

content = content.replace(old_gap1_section, new_gap1_section)

with open('data_collection/data_collection.md', 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated data_collection.md')
print()
print('Key changes:')
print('  - Removed synthetic G-Sec (was 7x too volatile)')
print('  - Replaced with real gilt fund NAVs (SBI/ICICI/HDFC/UTI)')
print('  - Final count: 134 assets, 133 with stats')
print('  - Added GAP-1 detail section explaining the removal')
print('  - Updated all matrix dimensions from 198x198 to 134x134')
