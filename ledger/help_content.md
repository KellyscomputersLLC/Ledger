# Understanding account types
There are five kinds of account. Every transaction moves money between two or more of them.

- Assets: what the business owns
- Liabilities: what the business owes
- Equity: the owner's stake in the business
- Income: money the business earns
- Expenses: money the business spends

Account numbers follow a convention: 1000s are assets, 2000s liabilities, 3000s equity, 4000s income, 5000s cost of sales, and 6000s operating expenses.

# Debits and credits reference
Every account has a "normal" side. Increasing the account is recorded on that side; decreasing it is recorded on the other side. The table below is the whole rule in one place.

## The rule

| Type | Increases | Decreases |
|---|---|---|
| Asset | Debit | Credit |
| Liability | Credit | Debit |
| Equity | Credit | Debit |
| Income | Credit | Debit |
| Expense | Debit | Credit |

## Examples by type
- Assets: cash, inventory, equipment
- Liabilities: sales tax payable, credit card payable
- Equity: owner's capital, retained earnings
- Income: sales revenue, service revenue
- Expenses: rent, utilities, cost of goods sold

> Not sure which account a transaction belongs to? When the right answer depends on your particular situation, check with your tax expert before recording it.

# Recording sales and income
Income is money the business earns. A sale always has two halves: the income you earned, and what you received for it. You credit the income account and debit whatever came in.

## The basic pattern
- Debit the asset you received -- Checking Account, or Accounts Receivable if you will be paid later
- Credit the income account -- Sales Revenue for goods, Service Revenue for work performed

## A worked example
Say a customer pays 250.00 in cash for goods. On the Record Entry screen you fill in the top fields, then two account rows:

- Description: Cash sale
- Reference: receipt or invoice number (optional)

| Account | Debit | Credit |
|---|---|---|
| Checking Account | 250.00 | |
| Sales Revenue | | 250.00 |

At the bottom, Debits and Credits both read 250.00. Because they match, the entry balances and "Record entry" will save it. If they did not match, Ledger would not let you record it.

## Paid now, or billed for later
If the customer pays at the time of sale, debit Checking Account. If you send an invoice and collect later, debit Accounts Receivable instead. When that invoice is paid, move the amount out of Accounts Receivable and into Checking Account -- the income was already recorded when you billed it, so the payment is not a second sale.

- Cash sale: debit Checking Account, credit Sales Revenue
- Invoice sent: debit Accounts Receivable, credit Sales Revenue
- Invoice paid: debit Checking Account, credit Accounts Receivable

## Sales tax you collect
Sales tax you add to a customer's bill is not your income. You are holding it for the tax authority, so it is a liability until you pay it on. Split the customer's payment: your part is income, the tax part is Sales Tax Payable.

- Debit Checking Account for the full amount received
- Credit Sales Revenue for your portion
- Credit Sales Tax Payable for the tax portion

## Sales through a card reader or POS
Card and POS systems (Square, Clover, and the like) usually deposit a whole day's takings as one lump, already reduced by their processing fee. That single deposit covers several things at once: your sales, the tax you collected, and the fee taken out. Record the deposit as the net amount that actually reached the bank, and the fee as an expense.

Example: in one day you sell 500.00 of goods, collect 30.00 of sales tax (customers' cards were charged 530.00), and the processor keeps a 15.00 fee, depositing 515.00 to your bank. The entry has four lines:

- Checking Account -- debit 515.00 (the net amount actually deposited)
- Merchant & Payment Fees -- debit 15.00 (the processor's cut, an expense)
- Sales Revenue -- credit 500.00 (your full sales, before the fee)
- Sales Tax Payable -- credit 30.00 (the tax you are holding)

Debits are 515.00 + 15.00 = 530.00 and credits are 500.00 + 30.00 = 530.00, so it balances. The deposit line is the net 515.00, but Sales Revenue is still the full 500.00 -- the fee did not shrink your sales, it is its own expense. Your POS report lists the gross sales, tax, and fees separately; use those figures.

> Whether you must charge sales tax, at what rate, and how your sales are taxed depends on where and how you operate. Check with your tax expert before deciding how to record sales.

# Recording expenses and purchases
An expense is money the business spends to operate. A purchase is the mirror image of a sale: it still has two halves -- the cost you took on, and what you paid for it with. You debit the expense and credit whatever the money came out of.

## The basic pattern
- Debit the expense account -- the kind of cost it is: Rent, Utilities, Office Supplies, and so on
- Credit what you paid with -- Checking Account if you paid now, or Accounts Payable if you will pay later

## A worked example
Say you buy 40.00 of office supplies and pay straight from the bank. On the Record Entry screen, two account rows:

| Account | Debit | Credit |
|---|---|---|
| Office Supplies | 40.00 | |
| Checking Account | | 40.00 |

Debits and Credits both read 40.00, so the entry balances and will save. Office Supplies (an expense) has gone up by 40.00, and Checking Account has gone down by the same.

## Buying on account, to pay later
If a supplier sends a bill you will settle later, credit Accounts Payable instead of Checking Account. You owe the money now, and the expense has already happened. A 120.00 supplier bill for supplies:

| Account | Debit | Credit |
|---|---|---|
| Office Supplies | 120.00 | |
| Accounts Payable | | 120.00 |

Accounts Payable now shows 120.00 owed, and the expense is already on the books.

## Paying the bill later
When you pay that bill, move it out of Accounts Payable. This is not a second expense -- the cost was recorded when the bill arrived, so paying only clears what you owe:

| Account | Debit | Credit |
|---|---|---|
| Accounts Payable | 120.00 | |
| Checking Account | | 120.00 |

Accounts Payable is back to 0, and the expense was counted exactly once.

- Bill received: debit the expense, credit Accounts Payable
- Bill paid: debit Accounts Payable, credit Checking Account

## Buying on a credit card
A card purchase works the same way, except what you owe afterwards is the card, not a supplier. "Credit Card Payable" is too long to sit in the narrow table here, so the entry is shown as lines. A 30.00 client lunch put on the card:

- Debit Meals 30.00 (the expense)
- Credit Credit Card Payable 30.00 (what you now owe the card)

When you later pay the card from the bank, that is its own entry -- and like paying any bill, it is not a fresh expense:

- Debit Credit Card Payable for the payment
- Credit Checking Account for the same amount

Paying the card clears what you owe; the lunch was already recorded as an expense when you bought it.

## Goods you resell, versus running costs
Two kinds of spending land in different accounts, though both are debits. The cost of goods you buy to resell is Cost of Goods Sold (5000); the day-to-day costs of running the business are the operating expenses in the 6000s:

- Buying stock to resell: debit Cost of Goods Sold
- Paying rent, a utility bill, or supplies: debit the matching 6000s expense

> Which account a cost belongs in -- and whether it is deductible -- can depend on your situation. When a purchase does not clearly fit, check with your tax expert before recording it.

# Internal money movement
Some entries do not involve income or expense at all -- you are only moving your own money from one place to another. Both sides are your own accounts, so nothing touches Sales Revenue or an expense account.

## Transfer between your accounts
Moving money from Checking into another account (savings, or paying down a card) is one debit and one credit:

- Debit the account the money goes into
- Credit the account it came from

## Setting up petty cash
Move a fixed sum out of Checking into Petty Cash -- say a 200.00 check to fill the drawer:

| Account | Debit | Credit |
|---|---|---|
| Petty Cash | 200.00 | |
| Checking Account | | 200.00 |

Petty Cash now holds 200.00. This only moves money; it is not an expense.

## Spending from petty cash
Record each purchase as it happens, which lowers the drawer. A 12.00 box of supplies:

| Account | Debit | Credit |
|---|---|---|
| Office Supplies | 12.00 | |
| Petty Cash | | 12.00 |

The drawer drops to 188.00. Keep the receipt so the cash on hand plus the receipts always equal the full fund.

## Replenishing petty cash
When the drawer runs low -- say purchases have brought it down to 50.00 -- write a 150.00 check from Checking to top it back up:

| Account | Debit | Credit |
|---|---|---|
| Petty Cash | 150.00 | |
| Checking Account | | 150.00 |

Petty Cash is back to 200.00. The expenses were already recorded as you spent, so the refill is just money moving back in.

> How you track and substantiate petty cash spending can matter at tax time. Check with your tax expert on what records to keep.

# Owner activity
Money that moves between you and the business -- you putting your own money in, or taking money out for yourself -- is not income and not an expense. It changes your stake in the business, which is equity. Two accounts handle it: Owner's Capital for money you put in, and Owner's Draw for money you take out.

## The basic pattern
- Money you put in: debit the account it lands in (usually Checking Account), and credit Owner's Capital
- Money you take out for yourself: debit Owner's Draw, and credit the account it comes from

## Putting money into the business
Say you deposit 500.00 of your own money to get started:

| Account | Debit | Credit |
|---|---|---|
| Checking Account | 500.00 | |
| Owner's Capital | | 500.00 |

Checking Account is up 500.00, and Owner's Capital now shows 500.00 -- that is your stake in the business.

## Taking money out, an owner's draw
When you take money out for yourself, record it as a draw:

| Account | Debit | Credit |
|---|---|---|
| Owner's Draw | 200.00 | |
| Checking Account | | 200.00 |

Owner's Draw now reads 200.00. This lowers your stake; it is not a business expense and does not change your profit.

## A draw is not pay, and not an expense
If you work in your own business, money you take for yourself is usually a draw -- not a wage and not an expense. So it never appears on the income statement and never reduces your profit. Whether you should instead be paid through payroll depends on how your business is set up; see "When to get help."

## Paying a business cost from your own pocket
Sometimes you pay for something the business needs with personal money. Record the expense as normal, but since none of the business's own accounts were touched, credit Owner's Capital -- in effect you put that much in. A 25.00 box of supplies you paid for yourself:

| Account | Debit | Credit |
|---|---|---|
| Office Supplies | 25.00 | |
| Owner's Capital | | 25.00 |

The supplies are recorded as an expense, and your stake rises by what you covered.

> How an owner should take money out -- a draw, or a wage through payroll -- and how it is taxed depends on how your business is set up (sole proprietor, partnership, LLC, corporation). Check with your tax expert.

# Setting up your books
A few things are worth settling before you record day-to-day entries: the chart of accounts you will use, the date your books begin, and the balances you are starting with.

## Your chart of accounts
Ledger starts you off with a standard chart of accounts -- the same accounts you have seen all through this help, like Checking Account, Sales Revenue, and Office Supplies. On the Accounts tab you can rename them, add your own, or hide ones you do not use. It is much easier to settle the chart before you enter a lot of transactions than to rework it afterwards.

## Choosing a start date
Pick the date your books begin -- often the first day of your financial year, or simply the day you start using Ledger. Everything that happened before that date is summed up once, as your opening balances, rather than re-entered transaction by transaction.

## Entering opening balances
When you start, the business may already own things and owe things. Enter them as a single opening entry dated your start date: debit what you own, credit what you owe, and let Owner's Capital absorb the difference so the entry balances. If you are simply starting with money in the bank:

| Account | Debit | Credit |
|---|---|---|
| Checking Account | 800.00 | |
| Owner's Capital | | 800.00 |

Owner's Capital reads 800.00 -- your starting stake. A fuller opening entry follows the same idea. Suppose you begin with 800.00 in Checking and a 500.00 tool you already own (Equipment), and you owe 300.00 on a loan (Loans Payable):

- Debit Checking Account 800.00 and Equipment 500.00 (what you own)
- Credit Loans Payable 300.00 (what you owe)
- Credit Owner's Capital 1000.00 -- the balancing figure, which is your stake: 1300.00 owned minus 300.00 owed

Debits total 1300.00 and credits total 300.00 + 1000.00 = 1300.00, so the opening entry balances.

> Settling your chart of accounts and start date, and how to value what you bring into the business, is worth getting right once. Check with your tax expert before you enter a lot of history.

# Understanding your reports
Ledger builds its reports for you on the Reports tab, from the entries you record -- you never fill them in by hand. Record balanced entries and the reports follow. Each one can be run for a date range, so you can produce a full year or a single quarter.

## Trial Balance
Lists every account that has a balance, each shown in its natural debit or credit column, and totals the two columns. When total debits equal total credits, your entries are internally consistent. It is the quick "are the books in balance" check, and the first thing to look at if a figure seems off.

## Income Statement (Profit & Loss)
Income minus expenses over the period gives your profit, or your loss. This is the report that answers "did the business make money?" for a span of time. Note what is not here: sales tax you collected and owner draws never appear, because they are not income or expense.

## Balance Sheet
A snapshot as of a chosen date, rather than a span of time. It shows what you own (assets), what you owe (liabilities), and your stake (equity), arranged so that assets always equal liabilities plus equity. If the income statement is the story of the period, the balance sheet is where you stand at a moment.

## General Ledger
Every transaction, grouped account by account. When you want to see exactly what moved through a single account -- say every entry that touched Checking Account or Sales Revenue -- this is the report that lays it out line by line.

## How one entry reaches the reports
The reports are different views of the same entries. A 250.00 cash sale lifts Sales Revenue (seen on the income statement) and Checking Account (seen on the balance sheet) at once -- one entry, reflected wherever it is relevant. Record it correctly once, and every report stays right.

## A note on the Reconcile tab
Separate from the four reports, the Reconcile tab compares your books against your bank statement, so you can catch anything entered twice or not at all. It checks your records against the bank's; the reports summarise the records themselves.

> Which reports and which periods you need at tax time depends on your business and where you operate. Your tax expert can tell you exactly what to hand over.

# Common mistakes to avoid
A short checklist of slips that are easy to make and easy to avoid once you have seen them. Most trace straight back to a section above.

- Counting an invoice payment as a second sale. The income was recorded when you billed it; collecting later just moves money from Accounts Receivable into Checking Account.
- Treating sales tax you collected as income. It is money you are holding for the tax authority -- Sales Tax Payable, a liability, not Sales Revenue.
- Recording an owner's draw as an expense. A draw lowers your stake in the business; it does not touch your profit.
- Recording the net card-reader deposit as your sales. The processor's fee came out first -- your sales are the full amount, and the fee is its own expense.
- Calling a transfer or a petty-cash refill an expense. Moving your own money between your own accounts is neither income nor expense.
- Recording an expense twice. The cost is recorded when the bill arrives; paying it later only clears Accounts Payable or Credit Card Payable.
- An entry that will not save. Ledger only records entries where debits equal credits -- if "Record entry" is refusing, your two sides do not yet match.
- Mixing personal and business money. Keep them apart; when you must use personal money for the business, record it through Owner's Capital.
- Putting a cost in the wrong account. When the right account is not obvious, it is worth a moment's thought -- or a quick check -- rather than a guess you will have to unpick later.

# When to get help
There are two kinds of help, for two different kinds of question: the accounting and tax judgment calls, and the program itself.

## Your tax expert, for the judgment calls
Throughout this help, the amber notes mark the moments where the right answer depends on your situation. Those are the times to ask a tax expert -- for example:

- Choosing or changing your business structure
- Whether you must charge sales tax, at what rate, and how to file it
- Payroll, and how you should pay yourself
- Depreciating equipment, and what counts as deductible
- Closing out and reporting at year end
- Anything where the answer depends on your jurisdiction or circumstances

Recording the entry is the easy part; deciding how a thing should be treated is what a tax expert is for.

## Kelly's Computers LLC, for the program
Ledger was designed and built by Kelly's Computers LLC. For questions about the software itself -- something not working as you expect, a feature you cannot find, or installing or moving Ledger to a new computer -- that is who to ask. Those are program questions, not tax questions.

## Keep backups, so help is easy when you need it
Good backups make almost any problem recoverable. Backing up is deliberately a manual step in Ledger -- you decide when, from the Backup tab -- and doing it yourself is a natural moment to glance over your entries and confirm the day's work is right. But if you forget, or would rather not, that is fine: when you close Ledger with changes that have not been backed up, it quietly saves a copy for you first -- marked with "auto" in the name -- so quitting can never lose your work. Each backup is a timestamped copy of your data, and nothing is ever overwritten, so you can keep several and always know which is which.

Your backups live in your Documents folder, under "Ledger Backups" and then a folder named for your business. Inside that are two folders: "Manual Backups" holds the copies you make yourself, and "Automatic Backups" holds the on-exit copies. Keeping them apart means that if one folder is ever lost, the other -- and the restore points in it -- still remain. The automatic copies are tidied up after about a month so they do not build up; the backups you make yourself are always kept.

Get in the habit of backing up before anything significant, such as a restore or moving to a new computer, and keep a copy off this machine too -- a USB drive or a cloud folder -- using "Back up to...". Restoring makes a safety copy of your current file first, so even an unwanted restore can be undone.

When in doubt about a number, it is far cheaper to ask early than to unwind a year of entries later.
