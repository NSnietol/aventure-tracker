# Requirements Document

## Introduction

Adventure Tracker is a zero-cost orchestrator designed to help a traveler track cheap flights for weekend getaways from Barranquilla (BAQ) or Cartagena (CTG) to Medellín (MDE), and discover new adventure activities posted by agencies on Instagram. The system notifies the user via Telegram and maintains a personal inventory of completed and wished activities. The solution runs both locally and on GitHub Actions, using free services and scraping techniques with anti-detection measures.

## Glossary

- **Flight_Tracker**: Module responsible for monitoring flight prices on configured routes and detecting price drops
- **Activity_Tracker**: Module responsible for monitoring Instagram accounts for new adventure activity posts
- **Notification_Service**: Component that sends formatted messages to the user via Telegram bot
- **State_Manager**: Component that persists and retrieves shared state using GitHub Gist storage
- **Holiday_Service**: Component that determines Colombian holidays and bridge weekends (puentes)
- **OCR_Processor**: Component that extracts text from Instagram post images using Tesseract
- **Inventory_Manager**: Component that manages the user's done and wishlist activity inventories
- **Route**: A flight path defined by origin airport code, destination airport code, price threshold, and drop percentage threshold
- **Bridge_Weekend**: A Colombian holiday that extends a weekend (puente), allowing for longer trips
- **Price_Threshold**: Maximum acceptable price in COP for a flight to trigger a notification
- **Drop_Percentage**: Minimum percentage decrease from last seen price to trigger a notification

## Requirements

### Requirement 1: Flight Route Configuration

**User Story:** As a traveler, I want to configure flight routes via a YAML file, so that I can easily add or modify the routes I want to track without changing code.

#### Acceptance Criteria

1. THE Flight_Tracker SHALL read route configurations from a YAML file at startup
2. WHEN a route configuration is loaded, THE Flight_Tracker SHALL validate that origin, destination, price_threshold (COP), and drop_percentage fields are present
3. IF a route configuration is missing required fields, THEN THE Flight_Tracker SHALL log an error and skip the invalid route
4. THE Flight_Tracker SHALL support multiple routes in a single configuration file

### Requirement 2: Weekend Trip Date Logic

**User Story:** As a traveler, I want the system to find flights that match my weekend adventure schedule, so that I only receive relevant flight options.

#### Acceptance Criteria

1. WHEN searching for outbound flights, THE Flight_Tracker SHALL include flights departing on Thursday after 6PM or Friday before 4PM
2. WHEN Friday is a Colombian holiday, THE Flight_Tracker SHALL also include Thursday evening flights as valid outbound options
3. WHEN searching for return flights, THE Flight_Tracker SHALL include flights departing on Sunday after 2PM or Monday before 10AM
4. THE Flight_Tracker SHALL use the Holiday_Service to determine Colombian holidays and bridge weekends
5. WHEN a bridge weekend is detected, THE Flight_Tracker SHALL extend the valid return window to include Monday evening flights

### Requirement 3: Colombian Holiday Detection

**User Story:** As a traveler, I want the system to know Colombian holidays, so that it can identify bridge weekends and adjust flight search windows accordingly.

#### Acceptance Criteria

1. THE Holiday_Service SHALL contain hardcoded Colombian holidays for years 2025 and 2026
2. WHEN the requested year is not in the hardcoded list, THE Holiday_Service SHALL query the Nager.Date API as a fallback
3. IF the Nager.Date API request fails, THEN THE Holiday_Service SHALL log a warning and return an empty holiday list for that year
4. WHEN determining bridge weekends, THE Holiday_Service SHALL identify holidays that fall on Monday or Friday

### Requirement 4: Flight Price Alert Logic

**User Story:** As a traveler, I want to be notified when flight prices meet my criteria, so that I can book cheap flights promptly.

#### Acceptance Criteria

1. WHEN a flight price is below the configured price_threshold, THE Flight_Tracker SHALL trigger a notification
2. WHEN a flight price drops by more than the configured drop_percentage from the last seen price, THE Flight_Tracker SHALL trigger a notification
3. THE Flight_Tracker SHALL check both price_threshold and drop_percentage conditions for each flight
4. THE State_Manager SHALL persist the last seen price for each route-date combination

### Requirement 5: Flight Notification Content

**User Story:** As a traveler, I want flight notifications to include all relevant booking information, so that I can quickly evaluate and book the flight.

#### Acceptance Criteria

1. WHEN sending a flight notification, THE Notification_Service SHALL include the price in COP
2. WHEN sending a flight notification, THE Notification_Service SHALL include the airline name
3. WHEN sending a flight notification, THE Notification_Service SHALL include the flight departure date and times
4. WHEN sending a flight notification, THE Notification_Service SHALL include a direct link to the booking page
5. WHEN a previous price exists, THE Notification_Service SHALL include the percentage change from the previous price

### Requirement 6: Instagram Account Monitoring

**User Story:** As an adventure enthusiast, I want the system to monitor specific Instagram accounts, so that I discover new adventure activities posted by agencies.

#### Acceptance Criteria

1. THE Activity_Tracker SHALL read the list of Instagram accounts to monitor from a YAML configuration file
2. WHEN checking an Instagram account, THE Activity_Tracker SHALL detect posts created since the last check
3. THE State_Manager SHALL persist the last seen post ID for each monitored account
4. WHEN a new post is detected, THE Activity_Tracker SHALL retrieve the post image for OCR processing

### Requirement 7: Instagram Scraping Strategy

**User Story:** As a user, I want the system to reliably fetch Instagram posts using free methods, so that the service remains zero-cost and functional.

#### Acceptance Criteria

1. THE Activity_Tracker SHALL use the Instaloader library as the primary method to fetch Instagram posts
2. IF Instaloader fails to fetch posts, THEN THE Activity_Tracker SHALL fall back to Playwright-based scraping
3. IF both Instaloader and Playwright methods fail, THEN THE Activity_Tracker SHALL send a notification with the message "Instagram blocked, check manually"
4. WHEN using Playwright scraping, THE Activity_Tracker SHALL apply playwright-stealth library for anti-detection
5. WHEN using Playwright scraping, THE Activity_Tracker SHALL apply random delays between 1 and 3 seconds between DOM actions
6. THE Activity_Tracker SHALL use XPath-based element selection to avoid dependency on dynamic CSS classes

### Requirement 8: Image Text Extraction

**User Story:** As a user, I want the system to extract text from Instagram post images, so that it can identify adventure destinations and activity types.

#### Acceptance Criteria

1. THE OCR_Processor SHALL use Tesseract OCR to extract text from post images
2. THE OCR_Processor SHALL configure Tesseract with Spanish language support
3. WHEN processing an image, THE OCR_Processor SHALL apply pre-processing to improve text recognition accuracy
4. THE OCR_Processor SHALL return the extracted text for inventory matching

### Requirement 9: Personal Activity Inventory

**User Story:** As an adventure enthusiast, I want to maintain lists of completed and wished activities, so that I only receive relevant notifications about new adventures.

#### Acceptance Criteria

1. THE Inventory_Manager SHALL read completed activities from a done.yaml file
2. THE Inventory_Manager SHALL read wished destinations from a wishlist.yaml file
3. WHEN extracted text matches an entry in done.yaml, THE Activity_Tracker SHALL exclude the post from notification
4. WHEN extracted text matches an entry in wishlist.yaml, THE Activity_Tracker SHALL trigger a notification for the post
5. WHEN extracted text matches neither done.yaml nor wishlist.yaml, THE Activity_Tracker SHALL skip the post without notification

### Requirement 10: Activity Notification Content

**User Story:** As a user, I want activity notifications to include relevant post information, so that I can evaluate the adventure opportunity.

#### Acceptance Criteria

1. WHEN sending an activity notification, THE Notification_Service SHALL include the Instagram account name
2. WHEN sending an activity notification, THE Notification_Service SHALL include the extracted text from the post image
3. WHEN sending an activity notification, THE Notification_Service SHALL include a direct link to the Instagram post
4. WHEN sending an activity notification, THE Notification_Service SHALL include the matched wishlist entry

### Requirement 11: Shared State Management

**User Story:** As a user, I want the system to maintain state across runs, so that it does not send duplicate notifications or miss price changes.

#### Acceptance Criteria

1. THE State_Manager SHALL use a GitHub Gist as the shared storage backend
2. THE State_Manager SHALL authenticate to GitHub API using a Personal Access Token from environment variables
3. WHEN reading state, THE State_Manager SHALL retrieve the Gist content and parse it as JSON
4. WHEN writing state, THE State_Manager SHALL update the Gist content via GitHub API
5. THE State_Manager SHALL store last seen prices per route, last notification timestamps, and seen Instagram post IDs

### Requirement 12: Telegram Notification Delivery

**User Story:** As a user, I want to receive notifications via Telegram, so that I can be alerted on my preferred messaging platform.

#### Acceptance Criteria

1. THE Notification_Service SHALL read Telegram bot token and chat ID from environment variables
2. WHEN sending a notification, THE Notification_Service SHALL format the message with emojis and Markdown
3. THE Notification_Service SHALL enforce a rate limit of maximum 20 messages per minute
4. IF a Telegram API request fails, THEN THE Notification_Service SHALL log the error and continue processing

### Requirement 13: Dual Execution Environment

**User Story:** As a developer, I want the system to run both locally and on GitHub Actions, so that I can test locally and automate in the cloud.

#### Acceptance Criteria

1. THE Adventure_Tracker SHALL detect the execution environment by checking for the CI environment variable
2. WHEN CI environment variable equals "true", THE Adventure_Tracker SHALL read secrets from GitHub Actions environment
3. WHEN CI environment variable is not set, THE Adventure_Tracker SHALL read configuration from a local .env file
4. THE Adventure_Tracker SHALL use Python virtual environment for local execution

### Requirement 14: Error Handling and Exit Codes

**User Story:** As a user, I want the system to handle errors gracefully, so that temporary failures do not break the automation pipeline.

#### Acceptance Criteria

1. WHEN a TimeoutError occurs during scraping, THE Activity_Tracker SHALL log the error and continue to the next account
2. WHEN a CAPTCHA is detected during scraping, THE Activity_Tracker SHALL log the detection and skip the current account
3. WHEN running in GitHub Actions environment, THE Adventure_Tracker SHALL exit with code 0 even if errors occurred
4. WHEN running locally, THE Adventure_Tracker SHALL exit with code 1 if errors occurred for visibility

### Requirement 15: GitHub Actions Workflow

**User Story:** As a user, I want the system to run automatically on a schedule, so that I receive timely notifications without manual intervention.

#### Acceptance Criteria

1. THE GitHub Actions workflow SHALL trigger on a cron schedule every 6 hours
2. THE GitHub Actions workflow SHALL support manual trigger via workflow_dispatch
3. THE GitHub Actions workflow SHALL install Python 3.11, Playwright with Chromium browser, and Tesseract with Spanish language pack
4. THE GitHub Actions workflow SHALL access TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GITHUB_GIST_ID, and GITHUB_GIST_TOKEN from repository secrets

### Requirement 16: Anti-Detection Measures

**User Story:** As a user, I want the system to avoid detection by anti-bot measures, so that scraping remains functional over time.

#### Acceptance Criteria

1. WHEN using Playwright for scraping, THE Activity_Tracker SHALL apply playwright-stealth library before navigation
2. THE Activity_Tracker SHALL apply random jitter delays between 1 and 3 seconds between DOM interactions
3. THE Activity_Tracker SHALL use XPath selectors instead of CSS class selectors for element location
4. THE Activity_Tracker SHALL implement Page Object Model pattern for scraper organization

### Requirement 17: Configuration-Driven Design

**User Story:** As a user, I want all configurable values in external files, so that I can modify behavior without changing code.

#### Acceptance Criteria

1. THE Flight_Tracker SHALL read all route configurations from a routes.yaml file
2. THE Activity_Tracker SHALL read all Instagram account configurations from an accounts.yaml file
3. THE Inventory_Manager SHALL read activity inventories from done.yaml and wishlist.yaml files
4. IF a configuration file is missing, THEN THE Adventure_Tracker SHALL log an error and skip the corresponding module
