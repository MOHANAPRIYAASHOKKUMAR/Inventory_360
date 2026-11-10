-- =============================================================================
-- Inventory 360 | Synthetic source data generator
-- Produces ~18 months (FY25/26 start -> yesterday) of realistic UK retail
-- supply chain data for Sample Retail Group. Deterministic: values are derived
-- from hashes, so re-running yields the same dataset for a given run date.
--
-- Embedded storylines for the dashboards:
--   * Christmas peak for Toys & Seasonal, spring/summer peak for Garden & DIY
--   * Black Friday uplift in Electricals
--   * Long-lead Asian suppliers with lower OTIF and supply disruptions
--   * Sea-freight surcharge Dec-2025 -> Apr-2026 (Red Sea re-routing)
--   * Overstock on discontinued lines, stockouts on a subset of A-class SKUs
-- =============================================================================
USE SCHEMA INVENTORY_360_DB.RAW;

-- Deterministic pseudo-random in [0,1) from a string key
CREATE OR REPLACE FUNCTION RND(K VARCHAR)
RETURNS FLOAT
AS 'MOD(MOD(HASH(K), 1000003) + 1000003, 1000003)::FLOAT / 1000003.0';

-- -----------------------------------------------------------------------------
-- Warehouses (UK distribution network)
-- -----------------------------------------------------------------------------
TRUNCATE TABLE WMS_WAREHOUSES;
INSERT INTO WMS_WAREHOUSES (WAREHOUSE_CODE, WAREHOUSE_NAME, TOWN, UK_REGION, NATION, SITE_TYPE,
                            CAPACITY_PALLETS, LATITUDE, LONGITUDE, DEMAND_FACTOR, OPENED_DATE)
SELECT * FROM VALUES
 ('DC01','Daventry National DC','Daventry','East Midlands','England','National DC',120000,52.2565,-1.1636,1.60,'2009-03-01'::DATE),
 ('DC02','Milton Keynes GM & Fashion DC','Milton Keynes','South East','England','National DC',85000,52.0406,-0.7594,1.30,'2012-09-01'::DATE),
 ('DC03','Avonmouth Regional DC','Bristol','South West','England','Regional DC',45000,51.5065,-2.6987,0.90,'2014-05-01'::DATE),
 ('DC04','Trafford Park Regional DC','Manchester','North West','England','Regional DC',60000,53.4668,-2.3264,1.20,'2011-02-01'::DATE),
 ('DC05','Wakefield Regional DC','Wakefield','Yorkshire and the Humber','England','Regional DC',50000,53.6833,-1.4977,1.00,'2016-07-01'::DATE),
 ('DC06','Bellshill Regional DC','Bellshill','Scotland','Scotland','Regional DC',40000,55.8166,-4.0260,0.80,'2013-10-01'::DATE),
 ('DC07','Magor Regional DC','Magor','Wales','Wales','Regional DC',28000,51.5797,-2.8331,0.55,'2018-04-01'::DATE),
 ('DC08','Lisburn Regional DC','Lisburn','Northern Ireland','Northern Ireland','Regional DC',22000,54.5162,-6.0580,0.45,'2019-01-01'::DATE),
 ('IC01','Felixstowe Import Centre','Felixstowe','East of England','England','Import Centre',70000,51.9615,1.3509,0.35,'2015-06-01'::DATE);

-- -----------------------------------------------------------------------------
-- Suppliers
-- -----------------------------------------------------------------------------
TRUNCATE TABLE ERP_SUPPLIERS;
INSERT INTO ERP_SUPPLIERS (SUPPLIER_ID, SUPPLIER_NAME, COUNTRY_CODE, COUNTRY_NAME, PRIMARY_CATEGORY,
                           LEAD_TIME_DAYS, PAYMENT_TERMS_DAYS, CONTRACT_TIER, RELIABILITY_FACTOR, ACTIVE_FLAG)
SELECT *, TRUE FROM VALUES
 ('SUP001','Northfield Foods Ltd','GB','United Kingdom','Grocery & Ambient',7,30,'Strategic',0.97),
 ('SUP002','Highland Beverage Co','GB','United Kingdom','Grocery & Ambient',10,45,'Preferred',0.95),
 ('SUP003','Rotterdam Fine Foods BV','NL','Netherlands','Grocery & Ambient',14,60,'Approved',0.90),
 ('SUP004','Mediterraneo Alimentari SpA','IT','Italy','Grocery & Ambient',21,60,'Preferred',0.88),
 ('SUP005','Pennine Cosmetics Ltd','GB','United Kingdom','Health & Beauty',10,30,'Preferred',0.94),
 ('SUP006','Rhein Pharma Consumer GmbH','DE','Germany','Health & Beauty',14,60,'Strategic',0.96),
 ('SUP007','Lumiere Beaute SAS','FR','France','Health & Beauty',18,60,'Approved',0.86),
 ('SUP008','Mumbai Wellness Exports','IN','India','Health & Beauty',42,90,'Approved',0.78),
 ('SUP009','Clearwater Hygiene Ltd','GB','United Kingdom','Household',7,30,'Strategic',0.96),
 ('SUP010','Baltic Paper Products Sp z o.o.','PL','Poland','Household',12,45,'Preferred',0.91),
 ('SUP011','Iberia Limpieza SL','ES','Spain','Household',16,60,'Approved',0.87),
 ('SUP012','Guangzhou Homewares Co','CN','China','Home & Furniture',56,90,'Strategic',0.82),
 ('SUP013','Anatolia Textiles AS','TR','Turkey','Home & Furniture',28,60,'Preferred',0.85),
 ('SUP014','Hanoi Furniture JSC','VN','Vietnam','Home & Furniture',63,90,'Approved',0.74),
 ('SUP015','Lancashire Linens Ltd','GB','United Kingdom','Home & Furniture',10,30,'Approved',0.93),
 ('SUP016','Shenzhen Brightway Electronics','CN','China','Electricals',49,90,'Strategic',0.84),
 ('SUP017','Voltix Europe BV','NL','Netherlands','Electricals',14,60,'Preferred',0.92),
 ('SUP018','Ningbo Appliance Group','CN','China','Electricals',52,90,'Approved',0.79),
 ('SUP019','Taipei Digital Accessories','TW','Taiwan','Electricals',45,60,'Approved',0.83),
 ('SUP020','Dhaka Garments Ltd','BD','Bangladesh','Clothing & Footwear',70,90,'Strategic',0.80),
 ('SUP021','Istanbul Denim Mills','TR','Turkey','Clothing & Footwear',30,60,'Preferred',0.86),
 ('SUP022','Porto Footwear Lda','PT','Portugal','Clothing & Footwear',21,60,'Preferred',0.90),
 ('SUP023','Tiruppur Knitwear Exports','IN','India','Clothing & Footwear',60,90,'Approved',0.76),
 ('SUP024','Kestrel Toys Ltd','GB','United Kingdom','Toys & Seasonal',14,45,'Preferred',0.93),
 ('SUP025','Yiwu Festive Products','CN','China','Toys & Seasonal',60,90,'Strategic',0.81),
 ('SUP026','Dongguan Play Industries','CN','China','Toys & Seasonal',55,90,'Approved',0.77),
 ('SUP027','Midlands Garden Supplies Ltd','GB','United Kingdom','Garden & DIY',7,30,'Strategic',0.95),
 ('SUP028','Jiangsu Outdoor Living','CN','China','Garden & DIY',58,90,'Preferred',0.80),
 ('SUP029','Nordic Tools AB','SE','Sweden','Garden & DIY',14,60,'Approved',0.92),
 ('SUP030','Hartwell DIY Products','GB','United Kingdom','Garden & DIY',9,30,'Approved',0.94),
 ('SUP031','Puffin Pet Nutrition Ltd','GB','United Kingdom','Pet Care',7,30,'Strategic',0.97),
 ('SUP032','Hollandia Petfood BV','NL','Netherlands','Pet Care',12,45,'Preferred',0.93),
 ('SUP033','Galway Pet Products Ltd','IE','Ireland','Pet Care',9,45,'Approved',0.91),
 ('SUP034','Little Acorn Baby Care Ltd','GB','United Kingdom','Baby & Toddler',8,30,'Strategic',0.96),
 ('SUP035','Bavaria Kinderpflege GmbH','DE','Germany','Baby & Toddler',13,60,'Preferred',0.94),
 ('SUP036','Gdansk Hygiene Sp z o.o.','PL','Poland','Baby & Toddler',12,45,'Approved',0.89);

-- -----------------------------------------------------------------------------
-- Product master (360 SKUs across 10 categories)
-- -----------------------------------------------------------------------------
TRUNCATE TABLE ERP_PRODUCTS;
INSERT INTO ERP_PRODUCTS (SKU, PRODUCT_NAME, CATEGORY, SUBCATEGORY, BRAND, SUPPLIER_ID, UNIT_COST_GBP,
                          UNIT_PRICE_GBP, UNITS_PER_PALLET, MIN_ORDER_QTY, SHELF_LIFE_DAYS, VELOCITY_CLASS,
                          LIFECYCLE_STATUS, LAUNCH_DATE)
WITH cat (c, category, nouns, subcats, brands, min_cost, max_cost, markup, shelf_life, upp) AS (
  SELECT * FROM VALUES
  (0,'Grocery & Ambient',
     'Assam Tea Bags 80s|Rich Tea Biscuits 300g|Baked Beans 4pk|Penne Pasta 1kg|Porridge Oats 1kg|Ground Coffee 227g|Basmati Rice 2kg|Chopped Tomatoes 4pk|Digestive Biscuits 400g|Granola 750g',
     'Tea & Coffee|Biscuits|Tinned Foods|Pasta & Rice|Breakfast Cereals|Tea & Coffee|Pasta & Rice|Tinned Foods|Biscuits|Breakfast Cereals',
     'Sample Retail Essentials|Sample Retail Finest|Northfield|Highland', 0.55, 4.20, 1.40, 365, 120),
  (1,'Health & Beauty',
     'Shampoo 400ml|Conditioner 400ml|Daily Moisturiser 50ml|Whitening Toothpaste 100ml|Shower Gel 500ml|Vitamin C 60 Tabs|Hand Cream 75ml|Body Lotion 400ml|Toothbrush Heads 4pk|SPF30 Sun Cream 200ml',
     'Hair Care|Hair Care|Skin Care|Oral Care|Bath & Shower|Vitamins|Skin Care|Skin Care|Oral Care|Skin Care',
     'Sample Retail Essentials|Pennine Botanics|Lumiere|Rhein Care', 1.10, 9.50, 1.85, 900, 220),
  (2,'Household',
     'Bio Laundry Liquid 40 Washes|Fabric Conditioner 1.5L|Multi-Surface Cleaner 750ml|Kitchen Roll 4pk|Toilet Tissue 9pk|Dishwasher Tablets 60s|Washing Up Liquid 900ml|Bin Bags 40pk|Thick Bleach 2L|Laundry Pods 30s',
     'Laundry|Laundry|Cleaning|Kitchen Roll & Tissue|Kitchen Roll & Tissue|Dishwasher|Cleaning|Cleaning|Cleaning|Laundry',
     'Sample Retail Essentials|Clearwater|Brightway Home|Baltic Soft', 0.80, 7.50, 1.50, 720, 80),
  (3,'Home & Furniture',
     'Duvet Set Double|Non-Stick Frying Pan 28cm|Ceramic Table Lamp|Storage Box 45L|Oak Effect Bookcase|Cotton Bath Towel|Stoneware Dinner Set 12pc|LED Floor Lamp|Velvet Cushion|Bedside Table',
     'Bedding|Kitchenware|Lighting|Storage|Furniture|Bedding|Kitchenware|Lighting|Bedding|Furniture',
     'Albion Home|Oakmere|Sample Retail Home|Lancashire Living', 4.00, 85.00, 2.10, 3650, 30),
  (4,'Electricals',
     '2-Slice Toaster|1.7L Rapid Kettle|Bluetooth Speaker|Wireless Earbuds|USB-C Charger 65W|Air Fryer 4.2L|Smart Plug 2pk|Steam Iron 2400W|Wireless Mouse|Hand Blender',
     'Small Appliances|Small Appliances|Audio|Audio|Computing Accessories|Small Appliances|Smart Home|Small Appliances|Computing Accessories|Small Appliances',
     'Voltix|Brightway|Sample Retail Tech|Kestrel Audio', 6.00, 70.00, 1.60, 3650, 40),
  (5,'Clothing & Footwear',
     'Crew Neck T-Shirt|Slim Fit Jeans|Knitted Jumper|Waterproof Jacket|School Polo 3pk|Leather Trainers|Pyjama Set|Chino Trousers|Hooded Sweatshirt|Ankle Boots',
     'Womenswear|Menswear|Womenswear|Menswear|Kidswear|Footwear|Kidswear|Menswear|Womenswear|Footwear',
     'Thistle & Co|Northbrook|Sample Retail Basics|Porto Walk', 2.50, 28.00, 2.60, 3650, 150),
  (6,'Toys & Seasonal',
     'Building Bricks Set|Christmas Tree 6ft|LED Fairy Lights 200|Chocolate Advent Calendar|Jigsaw Puzzle 1000pc|Remote Control Car|Plush Teddy Bear|Family Board Game|Kids Halloween Costume|Christmas Crackers 12pk',
     'Toys|Christmas|Christmas|Christmas|Games & Puzzles|Toys|Toys|Games & Puzzles|Halloween|Christmas',
     'Kestrel Toys|Sample Retail Festive|Playtime|Yuletide', 2.00, 40.00, 2.00, 3650, 60),
  (7,'Garden & DIY',
     'Rattan Bistro Set|Garden Hose 30m|Cordless Drill 18V|Emulsion Paint 2.5L|Solar Stake Lights 10pk|Peat-Free Compost 50L|BBQ Charcoal 10kg|Bypass Pruning Shears|Plant Pots 3pk|Decking Oil 5L',
     'Garden Furniture|Outdoor Living|Tools|Decorating|Outdoor Living|Outdoor Living|Outdoor Living|Tools|Outdoor Living|Decorating',
     'Hartwell|Midlands Garden|Nordic Pro|Sample Retail Garden', 2.00, 90.00, 1.90, 1825, 40),
  (8,'Pet Care',
     'Adult Dog Food 12kg|Clumping Cat Litter 10L|Wet Cat Food 12pk|Dog Dental Treats 500g|Pet Bed Medium|Cat Scratching Post|Rabbit Food 2kg|Reflective Dog Lead|Tropical Fish Flakes 100g|Cat Biscuits 2kg',
     'Dog|Cat|Cat|Dog|Dog|Cat|Small Animal|Dog|Small Animal|Cat',
     'Puffin Pets|Hollandia|Sample Retail Pets|Galway Paws', 1.50, 35.00, 1.60, 540, 60),
  (9,'Baby & Toddler',
     'Nappies Size 4 Jumbo|Sensitive Baby Wipes 12pk|Anti-Colic Bottle 3pk|First Infant Milk 800g|Baby Shampoo 300ml|Toddler Sippy Cup|Baby Bath Wash 500ml|Teething Rings 2pk|Muslin Squares 6pk|Toddler Snacks 6pk',
     'Nappies & Wipes|Nappies & Wipes|Feeding|Feeding|Baby Toiletries|Feeding|Baby Toiletries|Feeding|Baby Toiletries|Feeding',
     'Little Acorn|Sample Retail Baby|Bavaria Kinder|Gdansk Soft', 1.50, 14.00, 1.50, 720, 80)
),
sup AS (
  SELECT SUPPLIER_ID, PRIMARY_CATEGORY,
         ROW_NUMBER() OVER (PARTITION BY PRIMARY_CATEGORY ORDER BY SUPPLIER_ID) AS rn,
         COUNT(*)     OVER (PARTITION BY PRIMARY_CATEGORY) AS n_sup
  FROM ERP_SUPPLIERS
),
g AS (
  SELECT ROW_NUMBER() OVER (ORDER BY SEQ4()) - 1 AS i FROM TABLE(GENERATOR(ROWCOUNT => 360))
),
b AS (
  SELECT i, MOD(i, 10) AS c, FLOOR(i / 10) AS j,
         'SRG-' || LPAD(TO_VARCHAR(i + 1), 6, '0') AS sku
  FROM g
),
p AS (
  SELECT b.*, cat.*,
         RND(b.sku || 'cost') AS r_cost, RND(b.sku || 'vel') AS r_vel,
         RND(b.sku || 'life') AS r_life, RND(b.sku || 'px') AS r_px
  FROM b JOIN cat ON cat.c = b.c
)
SELECT
  p.sku,
  SPLIT_PART(p.brands, '|', FLOOR(p.j / 10) + 1) || ' ' || SPLIT_PART(p.nouns, '|', MOD(p.j, 10) + 1),
  p.category,
  SPLIT_PART(p.subcats, '|', MOD(p.j, 10) + 1),
  SPLIT_PART(p.brands, '|', FLOOR(p.j / 10) + 1),
  sup.SUPPLIER_ID,
  ROUND(p.min_cost + (p.max_cost - p.min_cost) * POW(p.r_cost, 1.7), 2) AS unit_cost,
  GREATEST(0.99, CEIL((p.min_cost + (p.max_cost - p.min_cost) * POW(p.r_cost, 1.7)) * p.markup * (0.9 + 0.25 * p.r_px)) - 0.01),
  GREATEST(4, ROUND(p.upp * (0.7 + 0.6 * RND(p.sku || 'upp')))),
  GREATEST(1, ROUND(p.upp * (0.7 + 0.6 * RND(p.sku || 'upp')) / 4)),
  p.shelf_life,
  CASE WHEN p.r_vel < 0.20 THEN 'A' WHEN p.r_vel < 0.50 THEN 'B' ELSE 'C' END,
  CASE WHEN p.r_life < 0.06 THEN 'Discontinued'
       WHEN p.r_life < 0.14 THEN 'New'
       WHEN p.category IN ('Toys & Seasonal', 'Garden & DIY') THEN 'Seasonal'
       ELSE 'Core' END,
  CASE WHEN p.r_life >= 0.06 AND p.r_life < 0.14
       THEN DATEADD(day, -ROUND(30 + 300 * RND(p.sku || 'launch')), CURRENT_DATE())
       ELSE DATEADD(day, ROUND(2400 * RND(p.sku || 'launch')), '2017-01-01'::DATE) END
FROM p
JOIN sup ON sup.PRIMARY_CATEGORY = p.category AND sup.rn = MOD(p.j, sup.n_sup) + 1;

-- -----------------------------------------------------------------------------
-- Daily simulation grid (SKU x site x day). Extends 75 days past yesterday so
-- that forward-dated purchase orders (open / in-transit) can be generated.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TRANSIENT TABLE _GEN_GRID AS
WITH prm AS (
  SELECT '2025-04-01'::DATE AS start_dt, DATEADD(day, -1, CURRENT_DATE()) AS as_of
),
days AS (
  SELECT DATEADD(day, n, prm.start_dt) AS d, n AS di, prm.as_of
  FROM (SELECT ROW_NUMBER() OVER (ORDER BY SEQ4()) - 1 AS n FROM TABLE(GENERATOR(ROWCOUNT => 900))) s, prm
  WHERE DATEADD(day, n, prm.start_dt) <= DATEADD(day, 75, prm.as_of)
),
ranged AS (
  -- Ranging: national DCs carry the full range, regional DCs ~75%, import centre long-lead lines
  SELECT p.SKU, p.CATEGORY, p.VELOCITY_CLASS, p.LIFECYCLE_STATUS, p.LAUNCH_DATE, p.UNIT_COST_GBP,
         p.UNIT_PRICE_GBP, p.MIN_ORDER_QTY, p.UNITS_PER_PALLET, p.SUPPLIER_ID,
         s.LEAD_TIME_DAYS, s.RELIABILITY_FACTOR, s.COUNTRY_CODE,
         w.WAREHOUSE_CODE, w.DEMAND_FACTOR,
         CASE p.VELOCITY_CLASS WHEN 'A' THEN 25 + 35 * RND(p.SKU || 'd')
                               WHEN 'B' THEN 6 + 14 * RND(p.SKU || 'd')
                               ELSE 0.5 + 4.5 * RND(p.SKU || 'd') END
           * w.DEMAND_FACTOR * (0.8 + 0.4 * RND(p.SKU || w.WAREHOUSE_CODE || 'b')) AS base_demand,
         CASE p.VELOCITY_CLASS WHEN 'A' THEN 7 WHEN 'B' THEN 14 ELSE 28 END
           * IFF(s.LEAD_TIME_DAYS > 40, 2, 1) AS cycle_days,
         CASE p.VELOCITY_CLASS WHEN 'A' THEN 5 WHEN 'B' THEN 7 ELSE 10 END AS safety_days,
         RND(p.SKU || w.WAREHOUSE_CODE || 'risk') AS r_risk,
         -- Supplier x site delivery slot, so that lines consolidate onto one PO
         RND(p.SUPPLIER_ID || w.WAREHOUSE_CODE || 'ph') AS r_phase
  FROM ERP_PRODUCTS p
  JOIN ERP_SUPPLIERS s ON s.SUPPLIER_ID = p.SUPPLIER_ID
  CROSS JOIN WMS_WAREHOUSES w
  WHERE CASE
          WHEN w.SITE_TYPE = 'National DC' AND w.WAREHOUSE_CODE = 'DC02'
               THEN p.CATEGORY IN ('Clothing & Footwear','Home & Furniture','Electricals','Toys & Seasonal','Garden & DIY')
          WHEN w.SITE_TYPE = 'National DC' THEN TRUE
          WHEN w.SITE_TYPE = 'Import Centre' THEN s.LEAD_TIME_DAYS > 40
          ELSE RND(p.SKU || w.WAREHOUSE_CODE || 'range') < 0.75
        END
),
f AS (
  SELECT r.*, d.d, d.di, d.as_of,
         MOD(FLOOR(r.r_phase * 56), r.cycle_days) AS phase,
         CASE r.CATEGORY
           WHEN 'Toys & Seasonal' THEN DECODE(MONTH(d.d), 9, 1.2, 10, 1.7, 11, 2.8, 12, 3.3, 1, 0.45, 2, 0.6, 0.8)
           WHEN 'Garden & DIY'    THEN DECODE(MONTH(d.d), 3, 1.2, 4, 1.7, 5, 2.1, 6, 2.2, 7, 1.9, 8, 1.4, 11, 0.5, 12, 0.45, 1, 0.5, 2, 0.7, 0.9)
           WHEN 'Electricals'     THEN DECODE(MONTH(d.d), 11, 1.7, 12, 1.5, 1, 0.8, 1.0)
           WHEN 'Clothing & Footwear' THEN DECODE(MONTH(d.d), 3, 1.1, 4, 1.15, 8, 1.25, 9, 1.2, 11, 1.2, 12, 1.35, 1, 0.85, 1.0)
           ELSE DECODE(MONTH(d.d), 12, 1.15, 1, 0.92, 1.0)
         END AS season,
         DECODE(DAYOFWEEKISO(d.d), 1, 0.9, 5, 1.1, 6, 1.25, 7, 1.1, 1.0) AS weekday_f,
         1 + 0.06 * d.di / 365 AS growth_f,
         CASE r.LIFECYCLE_STATUS
           WHEN 'Discontinued' THEN GREATEST(0.04, 1 - d.di / 300)
           WHEN 'New' THEN LEAST(1, DATEDIFF(day, r.LAUNCH_DATE, d.d) / 60 + 0.15)
           ELSE 1 END AS life_f
  FROM ranged r
  JOIN days d ON d.d >= IFF(r.LIFECYCLE_STATUS = 'New', r.LAUNCH_DATE, '2025-04-01'::DATE)
),
s AS (
  SELECT f.*,
         base_demand * season * growth_f * life_f AS expected_daily,
         IFF(LIFECYCLE_STATUS = 'Discontinued', base_demand, base_demand * season * growth_f * life_f) AS stock_basis,
         CASE WHEN LIFECYCLE_STATUS = 'Discontinued' THEN 5
              WHEN r_risk > 0.93 THEN 3.5
              WHEN r_risk > 0.86 THEN 2.0 ELSE 1.0 END AS cover_mult,
         safety_days
           + CASE WHEN r_risk < 0.08 THEN -8 WHEN r_risk < 0.16 THEN -4 ELSE 0 END
           + IFF(RELIABILITY_FACTOR < 0.90
                 AND RND(SKU || WAREHOUSE_CODE || TO_VARCHAR(FLOOR(di / 21))) < (1 - RELIABILITY_FACTOR) * 1.2, -14, 0)
           + cycle_days * (1 - MOD(di + phase, cycle_days) / cycle_days) AS cover_raw,
         MOD(di + phase, cycle_days) = 0 AS is_receipt_day,
         RND(SKU || WAREHOUSE_CODE || TO_VARCHAR(d)) AS r_day,
         RND(SKU || TO_VARCHAR(DATE_TRUNC('week', d))) AS r_week
  FROM f
)
SELECT
  d, di, as_of, SKU, WAREHOUSE_CODE, CATEGORY, VELOCITY_CLASS, LIFECYCLE_STATUS, SUPPLIER_ID,
  LEAD_TIME_DAYS, RELIABILITY_FACTOR, COUNTRY_CODE, UNIT_COST_GBP, UNIT_PRICE_GBP, MIN_ORDER_QTY,
  UNITS_PER_PALLET, cycle_days, cover_mult, is_receipt_day, expected_daily,
  GREATEST(0, ROUND(stock_basis * IFF(cover_raw <= 0, 0, cover_raw * cover_mult) * (0.9 + 0.2 * r_day))) AS qty_on_hand,
  ROUND(expected_daily * weekday_f * (0.7 + 0.6 * r_day)) AS units_demanded,
  CASE WHEN LIFECYCLE_STATUS = 'Discontinued' THEN 0.40
       WHEN CATEGORY = 'Toys & Seasonal' AND MONTH(d) = 1 THEN 0.30
       WHEN CATEGORY = 'Garden & DIY' AND MONTH(d) = 9 THEN 0.20
       ELSE 0.08 * r_week END AS discount_pct,
  r_day
FROM s;

-- -----------------------------------------------------------------------------
-- WMS stock snapshots and POS sales (history only)
-- -----------------------------------------------------------------------------
TRUNCATE TABLE WMS_STOCK_SNAPSHOT_DAILY;
INSERT INTO WMS_STOCK_SNAPSHOT_DAILY (SNAPSHOT_DATE, WAREHOUSE_CODE, SKU, QTY_ON_HAND, QTY_ALLOCATED, QTY_RECEIVED, QTY_DAMAGED)
SELECT d, WAREHOUSE_CODE, SKU,
       qty_on_hand,
       ROUND(qty_on_hand * (0.05 + 0.15 * r_day)),
       IFF(is_receipt_day, ROUND(expected_daily * cycle_days * cover_mult), 0),
       IFF(r_day < 0.02, CEIL(qty_on_hand * 0.01), 0)
FROM _GEN_GRID WHERE d <= as_of;

TRUNCATE TABLE POS_SALES_DAILY;
INSERT INTO POS_SALES_DAILY (SALES_DATE, WAREHOUSE_CODE, SKU, UNITS_SOLD, UNITS_DEMANDED, NET_SALES_GBP)
SELECT d, WAREHOUSE_CODE, SKU,
       IFF(qty_on_hand = 0, 0, LEAST(units_demanded, qty_on_hand)) AS units_sold,
       units_demanded,
       ROUND(IFF(qty_on_hand = 0, 0, LEAST(units_demanded, qty_on_hand)) * UNIT_PRICE_GBP * (1 - discount_pct), 2)
FROM _GEN_GRID WHERE d <= as_of AND units_demanded > 0;

-- -----------------------------------------------------------------------------
-- Purchase orders (one PO per supplier x site x planned receipt date)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TRANSIENT TABLE _GEN_PO_HDR AS
WITH ev AS (
  SELECT d AS expected_date, as_of, SUPPLIER_ID, WAREHOUSE_CODE, COUNTRY_CODE, LEAD_TIME_DAYS, RELIABILITY_FACTOR
  FROM _GEN_GRID
  WHERE is_receipt_day AND expected_daily > 0
  GROUP BY ALL
),
h AS (
  SELECT ev.*,
         'PO' || TO_CHAR(expected_date, 'YYMMDD') || RIGHT(SUPPLIER_ID, 3) || WAREHOUSE_CODE AS po_number,
         DATEADD(day, -LEAD_TIME_DAYS, expected_date) AS order_date,
         RND(SUPPLIER_ID || WAREHOUSE_CODE || TO_VARCHAR(expected_date)) AS r_po,
         CASE WHEN COUNTRY_CODE IN ('GB', 'TR') THEN 'Road'
              WHEN COUNTRY_CODE IN ('IE','NL','DE','FR','IT','ES','PT','PL','SE')
                   THEN IFF(RND(SUPPLIER_ID || TO_VARCHAR(expected_date) || 'm') < 0.12, 'Rail', 'Road')
              ELSE IFF(RND(SUPPLIER_ID || TO_VARCHAR(expected_date) || 'm') < 0.07, 'Air', 'Sea') END AS transport_mode
  FROM ev
)
SELECT h.*,
       DECODE(transport_mode, 'Sea', 38, 'Air', 5, 'Rail', 6, IFF(COUNTRY_CODE = 'GB', 1, 4)) AS transit_days,
       -- Late deliveries are driven by supplier reliability
       IFF(r_po < RELIABILITY_FACTOR, FLOOR(RND(po_number || 'e') * 2) - 1,
           1 + FLOOR(RND(po_number || 'l') * IFF(transport_mode = 'Sea', 16, 7))) AS delay_days
FROM h
WHERE order_date <= as_of;

TRUNCATE TABLE ERP_PURCHASE_ORDER_LINES;
INSERT INTO ERP_PURCHASE_ORDER_LINES (PO_NUMBER, PO_LINE, SUPPLIER_ID, WAREHOUSE_CODE, SKU, ORDER_DATE, EXPECTED_DATE,
                                      RECEIVED_DATE, QTY_ORDERED, QTY_RECEIVED, UNIT_COST_GBP, PO_STATUS)
WITH l AS (
  SELECT h.po_number, h.SUPPLIER_ID, h.WAREHOUSE_CODE, g.SKU, h.order_date, h.expected_date, h.as_of,
         h.transit_days, h.delay_days,
         GREATEST(g.MIN_ORDER_QTY, CEIL(g.expected_daily * g.cycle_days * g.cover_mult / g.MIN_ORDER_QTY) * g.MIN_ORDER_QTY) AS qty,
         ROUND(g.UNIT_COST_GBP * (0.97 + 0.07 * RND(h.po_number || g.SKU)) * (1 + 0.035 * g.di / 365), 2) AS cost,
         RND(h.po_number || g.SKU || 'fill') AS r_fill
  FROM _GEN_PO_HDR h
  JOIN _GEN_GRID g
    ON g.SUPPLIER_ID = h.SUPPLIER_ID AND g.WAREHOUSE_CODE = h.WAREHOUSE_CODE
   AND g.d = h.expected_date AND g.is_receipt_day AND g.expected_daily > 0
)
SELECT po_number,
       ROW_NUMBER() OVER (PARTITION BY po_number ORDER BY SKU),
       SUPPLIER_ID, WAREHOUSE_CODE, SKU, order_date, expected_date,
       IFF(DATEADD(day, delay_days, expected_date) <= as_of, DATEADD(day, delay_days, expected_date), NULL),
       qty,
       IFF(DATEADD(day, delay_days, expected_date) <= as_of,
           IFF(r_fill < 0.86, qty, ROUND(qty * (0.80 + 0.18 * RND(po_number || SKU || 'q')))), NULL),
       cost,
       CASE WHEN DATEADD(day, delay_days, expected_date) <= as_of THEN 'RECEIVED'
            WHEN DATEADD(day, -transit_days, expected_date) <= as_of THEN 'IN_TRANSIT'
            ELSE 'OPEN' END
FROM l;

-- -----------------------------------------------------------------------------
-- TMS inbound shipments (one per PO)
-- -----------------------------------------------------------------------------
TRUNCATE TABLE TMS_SHIPMENTS;
INSERT INTO TMS_SHIPMENTS (SHIPMENT_ID, PO_NUMBER, CARRIER, TRANSPORT_MODE, ORIGIN_COUNTRY, DESTINATION_CODE,
                           DISPATCH_DATE, PLANNED_ARRIVAL, ACTUAL_ARRIVAL, PALLETS, FREIGHT_COST_GBP,
                           DUTY_COST_GBP, CO2_KG, SHIPMENT_STATUS)
WITH agg AS (
  SELECT l.PO_NUMBER,
         SUM(CEIL(l.QTY_ORDERED / p.UNITS_PER_PALLET)) AS pallets,
         SUM(l.QTY_ORDERED * l.UNIT_COST_GBP) AS goods_value,
         MAX(IFF(p.CATEGORY = 'Clothing & Footwear', 1, 0)) AS has_apparel
  FROM ERP_PURCHASE_ORDER_LINES l
  JOIN ERP_PRODUCTS p ON p.SKU = l.SKU
  GROUP BY l.PO_NUMBER
),
x AS (
  SELECT h.*, a.pallets, a.goods_value, a.has_apparel,
         DATEADD(day, -h.transit_days, h.expected_date) AS planned_dispatch,
         DATEADD(day, h.delay_days, h.expected_date) AS arrival,
         RND(h.po_number || 'frt') AS r_frt
  FROM _GEN_PO_HDR h JOIN agg a ON a.PO_NUMBER = h.po_number
)
SELECT
  'SHP-' || SUBSTR(po_number, 3),
  po_number,
  CASE transport_mode
    WHEN 'Road' THEN DECODE(MOD(ABS(HASH(po_number)), 4), 0, 'DHL Supply Chain', 1, 'GXO Logistics', 2, 'Wincanton', 'XPO Logistics')
    WHEN 'Rail' THEN 'DB Cargo UK'
    WHEN 'Sea'  THEN DECODE(MOD(ABS(HASH(po_number)), 4), 0, 'Maersk', 1, 'MSC', 2, 'CMA CGM', 'Hapag-Lloyd')
    ELSE DECODE(MOD(ABS(HASH(po_number)), 2), 0, 'DHL Global Forwarding', 'Kuehne+Nagel') END,
  transport_mode, COUNTRY_CODE, WAREHOUSE_CODE,
  planned_dispatch,
  expected_date,
  IFF(arrival <= as_of, arrival, NULL),
  pallets,
  ROUND(pallets
        * DECODE(transport_mode, 'Sea', 48, 'Air', 440, 'Rail', 60, IFF(COUNTRY_CODE = 'GB', 24, 82))
        * (0.85 + 0.30 * r_frt)
        * IFF(transport_mode = 'Sea' AND planned_dispatch BETWEEN '2025-11-15' AND '2026-04-15', 1.45, 1.0)
        * (1 + 0.04 * DATEDIFF(day, '2025-04-01', planned_dispatch) / 365), 2),
  ROUND(goods_value * CASE WHEN COUNTRY_CODE IN ('GB','IE','NL','DE','FR','IT','ES','PT','PL','SE') THEN 0
                           WHEN has_apparel = 1 THEN 0.12
                           ELSE 0.04 + 0.03 * RND(SUPPLIER_ID || 'duty') END, 2),
  ROUND(pallets * DECODE(transport_mode, 'Sea', 185, 'Air', 2750, 'Rail', 42, IFF(COUNTRY_CODE = 'GB', 24, 140))
        * (0.9 + 0.2 * r_frt), 1),
  CASE WHEN arrival <= as_of THEN 'DELIVERED'
       WHEN planned_dispatch <= as_of THEN 'IN_TRANSIT'
       ELSE 'BOOKED' END
FROM x;

-- -----------------------------------------------------------------------------
-- Finance: monthly warehouse operating cost actuals (closed months only)
-- -----------------------------------------------------------------------------
TRUNCATE TABLE FIN_WAREHOUSE_COSTS_MONTHLY;
INSERT INTO FIN_WAREHOUSE_COSTS_MONTHLY (PERIOD_MONTH, WAREHOUSE_CODE, COST_CATEGORY, ACTUAL_COST_GBP)
WITH thr AS (
  SELECT DATE_TRUNC('month', s.SALES_DATE) AS period_month, s.WAREHOUSE_CODE, SUM(s.UNITS_SOLD) AS units
  FROM POS_SALES_DAILY s
  WHERE s.SALES_DATE < DATE_TRUNC('month', CURRENT_DATE())
  GROUP BY ALL
),
shr AS (
  SELECT DATE_TRUNC('month', k.SNAPSHOT_DATE) AS period_month, k.WAREHOUSE_CODE, SUM(k.QTY_DAMAGED * p.UNIT_COST_GBP) AS shrink
  FROM WMS_STOCK_SNAPSHOT_DAILY k JOIN ERP_PRODUCTS p ON p.SKU = k.SKU
  GROUP BY ALL
),
base AS (
  SELECT t.period_month, t.WAREHOUSE_CODE, t.units, w.CAPACITY_PALLETS, COALESCE(s.shrink, 0) AS shrink
  FROM thr t
  JOIN WMS_WAREHOUSES w ON w.WAREHOUSE_CODE = t.WAREHOUSE_CODE
  LEFT JOIN shr s ON s.period_month = t.period_month AND s.WAREHOUSE_CODE = t.WAREHOUSE_CODE
),
cats (cost_category) AS (SELECT * FROM VALUES ('Labour'), ('Rent & Rates'), ('Utilities'), ('Equipment & Maintenance'), ('Shrinkage & Damages'))
SELECT b.period_month, b.WAREHOUSE_CODE, c.cost_category,
       ROUND(CASE c.cost_category
         WHEN 'Labour'                  THEN (b.units * 0.85 + b.CAPACITY_PALLETS * 1.6) * IFF(MONTH(b.period_month) IN (11, 12), 1.18, 1.0)
         WHEN 'Rent & Rates'            THEN b.CAPACITY_PALLETS * 1.9
         WHEN 'Utilities'               THEN b.CAPACITY_PALLETS * 0.75 * IFF(MONTH(b.period_month) IN (11, 12, 1, 2), 1.4, 1.0)
         WHEN 'Equipment & Maintenance' THEN b.CAPACITY_PALLETS * 0.55
         ELSE b.shrink * 1.8 + b.units * 0.03 END
         * (0.94 + 0.12 * RND(b.WAREHOUSE_CODE || c.cost_category || TO_VARCHAR(b.period_month))), 2)
FROM base b CROSS JOIN cats c;

-- -----------------------------------------------------------------------------
-- Finance: FY budgets (Apr-25 -> Mar-27) and rolling forecast
-- -----------------------------------------------------------------------------
TRUNCATE TABLE FIN_BUDGETS_MONTHLY;
INSERT INTO FIN_BUDGETS_MONTHLY (PERIOD_MONTH, BUDGET_AREA, DIMENSION_KEY, BUDGET_GBP, FORECAST_GBP, BUDGET_VERSION)
WITH months AS (
  SELECT DATEADD(month, ROW_NUMBER() OVER (ORDER BY SEQ4()) - 1, '2025-04-01'::DATE) AS period_month
  FROM TABLE(GENERATOR(ROWCOUNT => 24))
),
purch AS (
  SELECT DATE_TRUNC('month', l.ORDER_DATE) AS period_month, p.CATEGORY AS dim, SUM(l.QTY_ORDERED * l.UNIT_COST_GBP) AS actual
  FROM ERP_PURCHASE_ORDER_LINES l JOIN ERP_PRODUCTS p ON p.SKU = l.SKU
  GROUP BY ALL
),
frt AS (
  SELECT DATE_TRUNC('month', PLANNED_ARRIVAL) AS period_month, DESTINATION_CODE AS dim, SUM(FREIGHT_COST_GBP + DUTY_COST_GBP) AS actual
  FROM TMS_SHIPMENTS GROUP BY ALL
),
whs AS (
  SELECT PERIOD_MONTH AS period_month, WAREHOUSE_CODE AS dim, SUM(ACTUAL_COST_GBP) AS actual
  FROM FIN_WAREHOUSE_COSTS_MONTHLY GROUP BY ALL
),
src AS (
  SELECT 'Inventory Purchases' AS area, * FROM purch
  UNION ALL SELECT 'Freight & Duty', * FROM frt
  UNION ALL SELECT 'Warehousing', * FROM whs
),
dims AS (SELECT DISTINCT area, dim FROM src),
grid AS (
  SELECT m.period_month, d.area, d.dim,
         cur.actual AS actual_same,
         py.actual  AS actual_prior_year
  FROM months m CROSS JOIN dims d
  LEFT JOIN src cur ON cur.area = d.area AND cur.dim = d.dim AND cur.period_month = m.period_month
  LEFT JOIN src py  ON py.area  = d.area AND py.dim  = d.dim AND py.period_month = DATEADD(month, -12, m.period_month)
)
SELECT period_month, area, dim,
       ROUND(
         CASE WHEN period_month < DATE_TRUNC('month', CURRENT_DATE()) AND actual_same IS NOT NULL
                   -- Budget set before the year: actuals land within +/- ~7% (sea freight overspend in the surge)
                   THEN actual_same / ((0.95 + 0.12 * RND(area || dim || TO_VARCHAR(period_month)))
                                       * IFF(area = 'Freight & Duty' AND period_month BETWEEN '2025-12-01' AND '2026-05-01', 1.22, 1.0))
              ELSE COALESCE(actual_prior_year, actual_same, 0) * 1.05 END, 2) AS budget_gbp,
       IFF(period_month >= DATE_TRUNC('month', CURRENT_DATE()),
           ROUND(COALESCE(actual_prior_year, actual_same, 0) * 1.05 * (0.97 + 0.12 * RND(area || dim || TO_VARCHAR(period_month) || 'fc')), 2),
           NULL) AS forecast_gbp,
       IFF(period_month < '2026-04-01', 'FY25/26 B1', 'FY26/27 B1')
FROM grid
WHERE COALESCE(actual_same, actual_prior_year) IS NOT NULL;

-- Clean up generator scaffolding
DROP TABLE IF EXISTS _GEN_GRID;
DROP TABLE IF EXISTS _GEN_PO_HDR;
