# AgroEase Testing Checklist

## Before Testing

1. Back up the PostgreSQL database.
2. From the project folder, apply the migrations in order to the existing database:

   ```powershell
   psql -U <postgres_user> -d <database_name> -f .\migrations\001_machinery_review_rental.sql
   psql -U <postgres_user> -d <database_name> -f .\migrations\002_user_profiles.sql
   psql -U <postgres_user> -d <database_name> -f .\migrations\003_optional_images.sql
   psql -U <postgres_user> -d <database_name> -f .\migrations\004_notifications.sql
   psql -U <postgres_user> -d <database_name> -f .\migrations\005_chat_messages.sql
   psql -U <postgres_user> -d <database_name> -f .\migrations\006_demo_payments.sql
   psql -U <postgres_user> -d <database_name> -f .\migrations\007_equipment_rental_dates.sql
   psql -U <postgres_user> -d <database_name> -f .\migrations\008_worker_daily_rate.sql
   psql -U <postgres_user> -d <database_name> -f .\migrations\009_user_multiple_roles.sql
   psql -U <postgres_user> -d <database_name> -f .\migrations\010_worker_tractor_reviews.sql
   ```

   Replace the two placeholders with your PostgreSQL username and database name. The existing base tables must already exist.

3. Stop the isolated preview server with `Ctrl+C`, activate the virtual environment using `.\venv\Scripts\Activate.ps1`, then run `python app.py`.
4. Open `http://127.0.0.1:5000` and use separate browser profiles or sign out when switching roles.
5. To create an admin, register a regular account, then assign its role in PostgreSQL:

   ```sql
   UPDATE "user" SET role = 'Admin' WHERE email = 'your-admin-email@example.com';
   ```

   Sign out and back in with the role selector left at **Select role** so the session receives the Admin role.

## Authentication and Roles

- **Steps:** Register one account with Farmer and Worker selected, and another with Farmer and Equipment Owner selected. Try registering with mismatched confirmation passwords, no role selected, and `Admin` submitted as a role. Sign in under each selected role and use the dashboard role switch. Also sign in to a multi-role account using a role that was not selected for it.
- **Expected:** Passwords are hashed and mismatches are rejected; each account uses one email/password for its selected roles; login and dashboard switching only allow roles linked to the account; Worker profile setup is available after switching to Worker; public Admin registration is rejected; protected pages reject the wrong role.
- **If it fails:** Check `DATABASE_URL`, confirm PostgreSQL is running, and verify the account role in the `"user"` table. After changing a role directly in SQL, sign in again.

## Worker Booking

- **Steps:** Sign in as a Worker, edit the profile, add a skill/location/availability to create the worker listing. As a Farmer, search and book that worker for a future date. Sign in as that Worker and accept or reject the request.
- **Expected:** Search filters retain their values; the booking belongs only to the linked worker; the farmer sees its status; booking decisions create notifications.
- **If it fails:** A Worker with no linked listing should save their profile first. Check the worker's `user_id`, the selected future date, and the booking status.

## Tractor and Machinery Rentals

- **Steps:** As an Equipment Owner, add one tractor and one machinery item. As a Farmer, submit rental date ranges. As the owner, accept or reject each request.
- **Expected:** New requests appear for their owner; the farmer sees the decision; overlapping pending or accepted ranges are rejected; other dates remain available.
- **If it fails:** Confirm the correct owner account is signed in, the date range is valid and in the future, and migrations `002` and `007` completed. Rejected requests release their dates.

## Machinery Reviews

- **Steps:** As a Farmer, request a machinery rental; have its owner accept it; open **My Machinery Rentals** and submit a 1-5 star review with a comment. Try submitting another review for that rental.
- **Expected:** The accepted rental can be reviewed once; the listing and review page show the average and total count; the owner receives a notification.
- **If it fails:** Confirm migration `001` completed and the rental belongs to the signed-in farmer with status `Accepted` or `Completed`. Pending/rejected rentals cannot be reviewed.

## Worker and Tractor Reviews

- **Steps:** As a Farmer, get a worker booking or tractor rental accepted. From **My Bookings** or **My Tractor Rentals**, submit a 1-5 star review with a comment, then try to submit another review for the same booking/rental. Check the worker listing or tractor card, and sign in as the worker/equipment owner to open their review links.
- **Expected:** Only the farmer who owns an accepted booking/rental can submit one review; reviews and average ratings appear on the listing and review page; the worker or equipment owner can view feedback for their own listing and receives a notification.
- **If it fails:** Confirm migration `010` completed, the booking/rental belongs to the signed-in farmer and is accepted or completed, and the worker listing is linked to its user account.

## Search and Filters

- **Steps:** Create workers with different skills, locations, and availability; tractors with different names/brands/locations/rates; and machinery with different names/types/locations/rates. Submit combinations of filters.
- **Expected:** Each listing matches all selected filters, and submitted values remain in the form. No Clear button is required.
- **If it fails:** Check spelling and that the listing is available. Price filters accept numeric maximums; remove non-numeric values and retry.

## Profiles

- **Steps:** As Farmer, Worker, and Equipment Owner, open **View profile**, edit the fields allowed for that role, and save. For Worker, also change skill and availability.
- **Expected:** Name/phone/location are saved; email and role remain view-only; Worker saves or updates one linked public worker listing; a success message appears.
- **If it fails:** Check name/skill length, phone format, location, and migration `002`. Re-open the edit page to confirm stored values.

## Image Uploads

- **Steps:** Add a tractor and machinery image, and upload a Worker profile image. Then try a `.exe` file and an image larger than 5 MB. View the related listing cards.
- **Expected:** JPG/JPEG/PNG/WEBP images appear on listings; invalid extensions return an error; uploads over 5 MB are rejected; records without images still display.
- **If it fails:** Confirm the app can write to `static/uploads/`. The folder is created automatically on startup. Check the file extension and size, then verify migrations `002` and `003` completed.

## Notifications

- **Steps:** Trigger a worker booking, tractor/machinery rental, owner accept/reject, and machinery review. Open **Notifications**, then mark one unread item as read.
- **Expected:** The intended account receives each event; the dashboard unread number decreases after marking read; another account cannot mark that notification read.
- **If it fails:** Check migration `004`, the event recipient's user ID, and that you are signed in as the account that received the notification.

## Chat

- **Steps:** As a Farmer, open a linked Worker listing or equipment listing and choose **Message**. Send a message, then sign in as the recipient and reply from **Messages**.
- **Expected:** Both participants see the conversation history in time order; unrelated accounts cannot view it; unsupported role pairs are denied.
- **If it fails:** Check migration `005` and confirm the Worker listing has a linked user account. Chat is standard page-based messaging, not live push.

## Demo Payments

- **Steps:** Have an owner accept a tractor or machinery rental. As the Farmer, open that rental and choose **Pay demo**. Select Cash or UPI, test pending, failed, then successful outcomes; try paying again after success.
- **Expected:** The selected Cash or UPI method and payment status are recorded; totals use daily rate times inclusive rental days; status and demo transaction ID appear in history; a second successful payment is blocked. No actual money is charged or transferred.
- **If it fails:** Confirm migration `006`, accepted rental status, ownership, and migration `007` date columns. Only the rental's farmer can access its payment.

## Admin Console

- **Steps:** Promote a test account to `Admin` using the SQL above, sign in again, and open **Admin Dashboard**. Try the URL as a Farmer. Attempt to delete a review and an equipment listing with rental history.
- **Expected:** Admin sees counts and record tables; normal users receive `403`; reviews can be moderated; listings with rental history cannot be deleted.
- **If it fails:** Confirm the database role is exactly `Admin` and sign in again. Do not create admins through public registration.

## Invalid Input and Database Errors

- **Steps:** Try a past booking date, reversed rental dates, overlapping dates, rating `0`/`6`, empty comments, invalid uploads, duplicate reviews, and requests while signed out. Stop PostgreSQL briefly and visit a database-backed page.
- **Expected:** Invalid values are rejected; duplicate/overlapping actions do not create extra records; signed-out users are redirected to login. A database outage may return an error until PostgreSQL is restored.
- **If it fails:** Inspect the Flask terminal traceback, confirm the relevant migration ran, check PostgreSQL service/credentials in `.env`, restore the database connection, and retry. Do not repeatedly submit a request while the server reports a database failure.

## Responsive UI

- **Steps:** Open the worker, machinery, tractor, profile, notification, chat, payment, and admin pages at desktop width and a narrow mobile width.
- **Expected:** Cards and forms fit the viewport; tables can scroll horizontally; text and actions do not overlap.
- **If it fails:** Check that `static/css/style.css` loads in the browser Network panel and inspect the failing viewport width.