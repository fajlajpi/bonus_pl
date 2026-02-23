# Tasks.py

## What does it do?
This script processes uploaded invoice data and creates transactions in the database. Transactions mean points gained (for turnover in brands under conditions in the contract) or points used up (for prizes claimed).

## Questions to ask
- **What is the actual algorithm of the processing?**
    - The points are accumulated:
        - Per user and they have to be registered (model "User")
        - Per brand and they have to be in the database (model "Brand")
        - Per invoice (see below) and each invoice has a unique alphanumeric designation (df column "Faktura")
        - At a ratio set by a BrandBonus model which has to be in the User's Contract (model UserContract, field "brandbonuses")
    - Therefore, to calculate the actual transaction, we need to know:
        - For each invoice, its value in each Brand
        - For the user related to the invoice, their active BrandBonuses
    - Therefore, the logical algorithm is:
        - Get unique client numbers (df column "ZČ")
        - Drop the clients that aren't in the system (model "User", field "user_number" must match df column "ZČ")
        - For the clients that remain, get unique invoice ids for them (df column "Faktura" and "ZČ")
        - For each of the clients, look up their Brand Bonuses
        - From the bonuses, look up their relevant brands and their prefixes (model "Brand" field "prefix")
        - For each unique invoice ID, sum up the values (df column "Cena") of the lines where the beginning of the code (df column "Kód") matches each relevant brand
        - Apply the relevant conversion ratio to the total sum of each brand (model BrandBonus field "points_ratio")
        - Per brand, save a transaction (model "PointsTransaction"):
            - Adding points the type is "STANDARD_POINTS"
            - Status is "PENDING" and points become active later (that is for a different script)
            - Description is "Invoice ID"
            - Brand is the relevant brand
    


- **How granular should the transactions be?**
    - Original idea: Monthly - sum up all transactions in a month, regardless of invoices
    - New idea: Per invoice - sum up points gained in each invoice. Shouldn't be too much added data (as most clients invoice 1-2x per month), but would allow greater ability to check and refine if needed
    - **Decision: PER INVOICE**

- **Should we save transactions for every client, or only for clients aready with contracts?**
    - Original idea: For every client, so that if they choose to join, we can retroactively "enable" their points going back.
    - Issue with this: We have multiple brands, and multiple levels. It's impossible to know which brands / levels the client will choose, if they join, and it's impractical to track all of it
    - New idea: Only contracted (registered) clients and add a script that, when a client joins, we re-scan the month they joined only for them and add points for them
    - Possible workaround: We can add the points they would have gained in the month manually with an adjustment, as they join.
    - **Decision: Only clients w/ contracts.**
