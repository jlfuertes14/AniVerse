You are absolutely right that APIs are usually cleaner, but OAuth2 (Redirect URIs, Scopes, etc.) is only required if you want your users to login and sync their personal watch-lists.

The Good News: You don't need OAuth2 for the Schedule!
To just get the Weekly Airing Times for everyone to see:

API Way: You still need an "Application Token" (a static string), which requires you to create an account and manually generate it in their settings.
Scraping Way: Requires zero setup. No account, no tokens, no redirect URIs. My scraper just "looks" at the page once a day and saves the data.
My Recommendation: Let's use the Scraper
Since you are building a discovery engine, you probably don't want to force your users to have an AnimeSchedule.net account. By using a Playwright Scraper, we can:

Get the exact same data as the API.
Avoid all the OAuth2/Token complexity.
Keep your project standalone and easy to run for anyone.
I can have the scraper finished in a few minutes. It will look like this:

Background Task: Runs at 3 AM every day.
Logic: Visits animeschedule.net, grabs the week's data, and updates your MongoDB.
UI: Your "Estimated Schedule" section will automatically populate with countdowns.
Shall I build the "Zero-Config" Scraper for you now?

6:37 PM
okays lets go with scrapper since the schedule of the anime airing is per season like (winter, spring and fall anime and etc) we dont have to scrape daily since the anime runs at the same schedule(day adnd time) the only changing is the date (May, 9 example)