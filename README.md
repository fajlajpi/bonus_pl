# PA Bonus Programme 2025

## One-line summary
Django-based system for tracking and using loyalty points

## Target functionality
### For end-users
- Users can register within the system (rather than externally via Google Forms)
- Users can manage their registration, contracts, bonuses within the system
    - All pending approval from Management
- Users can see their points increase and understand where the points came from
- Users can claim rewards for their points from a bonus catalogue
- Users can receive notifications of points gained (monthly) and spent
    - Via email, SMS, WhatsApp

### For Management
*Ideally, Managers do not need to use Django Admin for anything*
- Managers can set up Brand Bonuses
- Managers can register clients for the system
- Managers can set up Rewards for clients to claim
- Managers can see, review and confirm / deny applications to bonus program
- Managers can see reward claims and confirm / deny them
- Managers can import turnover data, credit note data


### For Sales Reps
*Sales Reps need to see the status of their own clients, but not anyone else's. They also need to have an easy way of helping their clients with the system.*
- Sales Reps can look at their clients
- Reps can see the clients' turnover in brands as well as their point totals
- Reps can see the clients' open reward requests, without being able to modify
- Reps can create reward requests in the name of their clients.

### For Admins
- Admins can see individual transactions
- Admins can upload exports from accounting (raw invoice data) and check their processing

## MVP Functionality
- Uploading accounting data
    - Invoices (points gained for turnover in brands)
    - Invoices (points lost for rewards claimed)
    - Credit Notes (points lost for money returned to client)
- Processing accounting data and creating point transactions
- Users can log in and see their points totals as well as transactions history
- Users can see a list of available rewards
- Users can send a reward request
- Basic styling

## MVP V2: Going Public
- [x] SMS Notifications (monthly + one shot login info) via CSV
- [x] Email notifications
- [x] Login with email
- [x] Reward Request confirmation
- [x] Reward Request to Telemarketing bridge file
- [x] Translations in all relevant places
- [ ] Landing page, better login page
- [x] Static pages such as contacts, privacy policy
- [x] Necessary warning / under construction messages

## First big update: V3
- [ ] Client EXTRA GOAL logic
- [ ] Sales Rep functionality
    - [ ] See current client status (limited to own region)
    - [ ] See own region stats
    - [ ] See clients' extra goal progress
    - [ ] Place RewardRequests for clients
- [ ] User options and abilities
    - [ ] Opt in/out of notifications via email/sms
    - [ ] Click-through agreement with privacy policy / extra goal
    - [ ] Cancellation of RewardRequests before they're accepted
    - [ ] Modification of RewardRequests before they're submitted
    - [ ] Password change / request if forgotten

## TODO
- [DONE] Basic Models layout
- [DONE] Upload functionality
- [DONE] Invoice data processing
- Credit Note processing
- User Views
    - Current Point Balance
    - Individual Transactions
- Reward Claims
    - Reward Catalogue
    - Reward Request
    - Reward Request status and review
- Move to PostgreSQL
- Client notifications
    - When points are added via email
    - Look into SMS options
- Basic styling

## Nice to have
- Custom views instead of Django Admin for Managers
- Internationalization prepared (but postponed due to Hungary launch being shelved for now)
- Proper Template structure
- Anything resembling Front-end
- Proper verification
    - Transaction "fingerprinting" to prevent duplicate transactions
