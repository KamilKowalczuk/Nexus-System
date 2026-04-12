Actors in Store

Copy for LLM
Publishing and monetizing Actors

Anyone is welcome to publish Actors in the store, and you can even monetize your Actors. For more information about how to monetize your Actor, best practices, SEO, and promotion tips and tricks, head over to the Marketing checklist section of the Apify Developers Academy.
Pricing models

All Actors in Apify Store fall into one of the four pricing models:

    Pay per event - you pay for specific events the Actor creator defines, such as generating a single result or starting the Actor. Most Actors include platform usage in the price, but some may charge it separately - check the Actor's pricing for details.
    Pay per result - you do not pay for platform usage the Actor generates and instead just pay for the results it produces.
    Pay per usage - you only pay for the platform resources (compute units, data transfer, etc.) the Actor consumes. There are no additional charges from the Actor developer.
    Rental - to continue using the Actor after the trial period, you must rent the Actor from the developer and pay a flat monthly fee in addition to the costs associated with the platform usage that the Actor generates.

Post-run storage costs

After a run finishes, any interactions with the dataset - such as reading or writing additional data - incur standard platform usage costs. This applies to all pricing models. Unnamed datasets are automatically removed after your data retention period, so long-term storage is rarely a concern.
Pay per event

With pay per event pricing, you pay for specific events defined by the Actor creator, such as producing a single result, uploading a file, or starting an Actor. These events and their prices are always described on each Actor's page.

Example pay per event Actor
Some Actors charge platform usage separately

Most pay per event Actors include platform usage in the event price. However, some Actors may require you to pay for platform usage separately. Always check the Actor's pricing section to understand what's included.

Pay per event with usage not included in Apify Store

When starting a run, you can define a maximum charge limit. The Actor terminates gracefully when it reaches that limit - and even if it does not stop immediately, you are never charged for produced events over the defined limit.

Pay per event Actor - max charge per run

Your charges appear on your invoices and in the Historical usage tab in the Billing section of Apify Console. The cost of each run also appears on the run detail page.

Pay per event Actor - historical usage tab

Pay per event Actor - run detail

If charges seem incorrect, contact the Actor author or the Apify support team. You can also open an issue directly on the Actor's detail page in Apify Console.
Pay per result

When you run an Actor that is paid per result, you pay for the successful results the Actor returns, and you are not charged for the underlying platform usage.
Estimation simplified

This makes it transparent and easy to estimate upfront costs. If you have any feedback or would like to ask something, please join the Discord community and let us know!

Actor paid per result in Console

All platform costs generated during the Actor run are not charged to your account.

You can limit how many results an Actor returns - and therefore control how much you're charged - by setting a maximum items limit in the Options section below the Actor input on the Actor detail page.

Max items for pay-per-result

Your charges appear on your invoices and in the Historical usage tab in the Billing section of Apify Console, where pay per result charges are shown as a separate service. The cost also appears on individual run detail pages and in the overview of all runs.

Statistics in the billing section

Run cost shown on the run detail

Run cost shown on the overview of all runs

To see total charges for a specific Actor, check the bottom of the Historical usage tab.

Actor pay-per-result cost

Pay per result is also available as a pricing option when you publish your own Actors - see Monetizing your Actor for details.
Pay per usage

When you use a pay per usage Actor, you are only charged for the platform usage that the runs of this Actor generate. Platform usage includes components such as compute units, operations on storages, and usage of residential proxies or SERPs.

Pay for usage Actor example
Estimating Actor usage cost

With this model, it's very easy to see how many platform resources each Actor run consumed, but it is quite difficult to estimate their usage beforehand. The best way to find the costs of free Actors upfront is to try out the Actor on a limited scope (for example, on a small number of pages) and evaluate the consumption. You can easily do that using our free plan.

For more information on platform usage cost see the usage and resources page.
Rental Actors
Rental model sunset

Apify is sunsetting the rental pricing model. The following changes are scheduled for 2026:

    April 1 - You can no longer publish new rental Actors or change pricing on existing ones.
    October 1 - Rental Actors are fully retired. All remaining Actors are migrated to pay-per-usage pricing.

For more information, visit the #project-rentals channel on Apify Discord.

Rental Actors are Actors for which you have to pay a recurring fee to the developer after your trial period ends.

Most rental Actors have a free trial period. The length of the trial is displayed on each Actor's page.

Rental Actor example

You don't need a paid plan to start a rental Actor's free trial. After the trial, you must subscribe to one of Apify's paid plans to continue renting and using the Actor. If you are on a paid plan, the monthly rental fee is automatically subtracted from your prepaid platform usage when the trial expires, then recurs monthly. If you are not on a paid plan when the trial ends, you are not charged but cannot use the Actor until you subscribe.

You always prepay the rental fee for the following month. The first payment occurs when the trial expires, then recurs monthly. You can check when the next payment is due by opening the Actor in Apify Console - you'll also receive a notification when it happens.

Example: You activate a 7-day trial at noon on April 1, 2021. Without cancellation, you are charged at noon on April 8, 2021, then May 8, 2021.

Rental fees are subtracted automatically from your prepaid platform usage, similarly to compute units. Most of the fee goes directly to the developer, and you also pay normal platform usage costs on top - usage cost estimates are usually included in each rental Actor's README (see an example). If your prepaid usage is insufficient, any overage is covered in the next invoice.

You can cancel the rental at any time during the trial or afterward so you are not charged when the current rental period expires. You can always turn it back on later.

To see a breakdown of rental charges, go to the Actors tab within the Current period tab in the Billing section.

Rental Actors billing in Apify Console
Report issues with Actors

Each Actor has an Issues tab in Apify Console. There, you can open an issue (ticket) and chat with the Actor's author, platform admins, and other users of this Actor. Please feel free to use the tab to ask any questions, request new features, or give feedback. Alternatively, you can always write to community@apify.com.

Paid Actors&#39; issues tab
Apify Store discounts

Each Apify subscription plan includes a discount tier (BRONZE, SILVER, GOLD) that provides access to increasingly lower prices on selected Actors.
Discount participation

Discount offers are optional and determined by Actor owners. Not all Actors participate in the discount program.

Additional discounts are available for Enterprise customers.

To check an Actor's pricing and available discounts, visit the Pricing section on the Actor's detail page in Apify Store.

Apify Store discounts

In Apify Console, you can find information about pricing and available discounts in the Actor's header section.

Apify Store discounts

Apify Store discounts full table

Input and output

Copy for LLM
Input

Each Actor accepts input, which tells it what to do. You can run an Actor using the Apify Console UI, then configure the input using the autogenerated UI:

Input UI

When running an Actor using the API you can pass the same input as the JSON object. In this case, the corresponding JSON input looks as follows:

{
    "maxRequestsPerCrawl": 10,
    "proxy": {
        "useApifyProxy": true
    },
    "startUrl": "https://apify.com"
}

Options - Build, Timeout, and Memory

As part of the input, you can also specify run options such as Build, Timeout, and Memory for your Actor run.

Run options
Option	Description
Build	Tag or number of the build to run (e.g. latest or 1.2.34).
Timeout	Timeout for the Actor run in seconds. Zero value means there is no timeout.
Memory	Amount of memory allocated for the Actor run, in megabytes.
Dynamic memory

If the Actor is configured by developer to use dynamic memory, the system will calculate the optimal memory allocation based on your input. In this case, the Memory option acts as an override - if you set it, the calculated value will be ignored.
Output

While the input object provides a way to instruct Actors, an Actor can also generate an output, usually stored in its default Dataset, but some additional files might be stored in its Key-value store. Always read the Actor's README to learn more about its output.

For more details about storages, visit the Storage section.

You can quickly access the Actor's output from the run detail page:

Actor output

And to access all the data associated with the run, see the Storage tab, where you can explore the Actor's default Dataset, Key-value store, and Request queue:

Actor output

You can also use API to retrieve the output. To learn more about this, read the Run an Actor or task and retrieve data via API tutorial.


Runs and builds

Copy for LLM
Builds

An Actor is a combination of source code and various settings in a Docker container. To run, it needs to be built. An Actor build consists of the source code built as a Docker image, making the Actor ready to run on the Apify platform.
What is Docker image?

A Docker image is a lightweight, standalone, executable package of software that includes everything needed to run an application: code, runtime, system tools, system libraries, and settings. For more information visit Docker's site.

With every new version of an Actor, a new build is created. Each Actor build has its number (for example, 1.2.34), and some builds are tagged for easier use (for example, latest or beta). When running an Actor, you can choose what build you want to run by selecting a tag or number in the run options. To change which build a tag refers to, you can reassign it using the Actor update API endpoint.

Actor run options

Each build may have different features, input, or output. By fixing the build to an exact version, you can ensure that you won't be affected by a breaking change in a new Actor version. However, you will lose updates.
Runs

When you start an Actor, an Actor run is created. An Actor run is a Docker container created from the build's Docker image with dedicated resources (CPU, memory, disk space). For more on this topic, see Usage and resources.

Each run has its own (default) storages assigned, which it may but not necessarily need to use:

    Key-value store containing the input and enabling Actor to store other files.
    Dataset enabling Actor to store the results.
    Request queue to maintain a queue of URLs to be processed.

What's happening inside of an Actor is visible on the Actor run log in the Actor run detail:

Actor run
Origin

Both Actor runs and builds have the Origin field indicating how the Actor run or build was invoked, respectively. The origin is displayed in Apify Console and available via API in the meta.origin field.
Name	Origin
DEVELOPMENT	Manually from Apify Console in the Development mode (own Actor)
WEB	Manually from Apify Console in "normal" mode (someone else's Actor or task)
API	From Apify API
CLI	From Apify CLI
SCHEDULER	Using a schedule
WEBHOOK	Using a webhook
ACTOR	From another Actor run
STANDBY	From Actor Standby
Lifecycle

Each run and build starts with the initial status READY and goes through one or more transitional statuses to one of the terminal statuses.

Terminal states

Transitional states

RUNNING

TIMING-OUT

ABORTING

SUCCEEDED

FAILED

TIMED-OUT

ABORTED

READY
Status	Type	Description
READY	initial	Started but not allocated to any worker yet
RUNNING	transitional	Executing on a worker machine
SUCCEEDED	terminal	Finished successfully
FAILED	terminal	Run failed
TIMING-OUT	transitional	Timing out now
TIMED-OUT	terminal	Timed out
ABORTING	transitional	Being aborted by the user
ABORTED	terminal	Aborted by the user
Aborting runs

You can abort runs with the statuses READY, RUNNING, or TIMING-OUT in two ways:

    Immediately - this is the default option. The Actor process is killed immediately with no grace period.
    Gracefully - the Actor run receives a signal about aborting via the aborting event and is granted a 30-second window to finish in-progress tasks before getting aborted. This is helpful in cases where you plan to resurrect the run later because it gives the Actor a chance to persist its state. When resurrected, the Actor can restart where it left off.

You can abort a run in Apify Console using the Abort button or via API using the Abort run endpoint.
Resurrection of finished run

Any Actor run in a terminal state, i.e., run with status FINISHED, FAILED, ABORTED, and TIMED-OUT, might be resurrected back to a RUNNING state. This is helpful in many cases, for example, when the timeout for an Actor run was too low or in case of an unexpected error.

The whole process of resurrection looks as follows:

    Run status will be updated to RUNNING, and its container will be restarted with the same storage (the same behavior as when the run gets migrated to the new server).
    Updated duration will not include the time when the Actor was not running.
    Timeout will be counted from the point when this Actor run was resurrected.

Resurrection can be performed in Apify Console using the resurrect button or via API using the Resurrect run API endpoint.
Settings adjustments

You can also adjust timeout and memory or change Actor build before the resurrection. This is especially helpful in case of an error in the Actor's source code as it enables you to:

    Abort a broken run
    Update the Actor's code and build the new version
    Resurrect the run using the new build

Data retention

Apify securely stores your ten most recent runs indefinitely, ensuring your records are always accessible. All Actor runs beyond the latest ten are deleted along with their default storages (Key-value store, Dataset, Request queue) after the data retention period based on your subscription plan.

Actor builds are deleted only when they are not tagged and have not been used for over 90 days.


Usage and resources

Copy for LLM
Resources

Actors run in Docker containers, which have a limited amount of resources (memory, CPU, disk size, etc). When starting, the Actor needs to be allocated a certain share of those resources, such as CPU capacity that is necessary for the Actor to run.

Setting an Actor&#39;s memory

Assigning an Actor a specific Memory capacity, also determines the allocated CPU power and its disk size.

Check out the Limits page for detailed information on Actor memory, CPU limits, disk size and other limits.
Memory

When invoking an Actor, the caller can specify the memory allocation for the Actor run. If not specified, the Actor's default memory is used (which can be dynamic). The memory allocation must follow these requirements:

    It must be a power of 2.
    The minimum allowed value is 128MB
    The maximum allowed value is 32768MB
    Acceptable values include: 128MB, 256MB, 512MB, 1024MB, 2048MB, 4096MB, 8192MB, 16384MB, and 32768MB

Additionally, each user has a certain total limit of memory for running Actors. The sum of memory allocated for all running Actors and builds needs to be within this limit, otherwise the user cannot start a new Actor. For more details, see limits.
CPU

The CPU allocation for an Actor is automatically computed based on the assigned memory, following these rules:

    For every 4096MB of memory, the Actor receives one full CPU core
    If the memory allocation is not a multiple of 4096MB, the CPU core allocation is calculated proportionally
    Examples:
        512MB = 1/8 of a CPU core
        1024MB = 1/4 of a CPU core
        8192MB = 2 CPU cores

CPU usage spikes

A usage spike on an Actor&#39;s start-up

Sometimes, you see the Actor's CPU use go over 100%. This is not unusual. To help an Actor start up faster, it is allocated a free CPU boost. For example, if an Actor is assigned 1GB (25% of a core), it will temporarily be allowed to use 100% of the core, so it gets started quicker.
Disk

The Actor has hard disk space limited by twice the amount of memory. For example, an Actor with 1024MB of memory will have 2048MB of disk available.
Requirements

Actors built with Crawlee use autoscaling. This means that they will always run as efficiently as they can based on the allocated memory. If you double the allocated memory, the run should be twice as fast and consume the same amount of compute units (1 * 1 = 0.5 * 2).

A good middle ground is 4096MB. If you need the results faster, increase the memory (bear in mind the next point, though). You can also try decreasing it to lower the pressure on the target site.

Autoscaling only applies to solutions that run multiple tasks (URLs) for at least 30 seconds. If you need to scrape just one URL or use Actors like Google Sheets that do just a single isolated job, we recommend you lower the memory.

If the Actor doesn't have this information, or you want to use your own solution, just run your solution like you want to use it long term. Let's say that you want to scrape the data every hour for the whole month. You set up a reasonable memory allocation like 4096MB, and the whole run takes 15 minutes. That should consume 1 CU (4 * 0.25 = 1). Now, you just need to multiply that by the number of hours in the day and by the number of days in the month, and you get an estimated usage of 720 (1 * 24 * 30) compute units monthly.
Estimating usage

Check out the article on estimating consumption for more details.
Memory requirements

Each use case has its own memory requirements. The larger and more complex your project, the more memory/CPU power it will require. Some examples which have minimum requirements are:

    Actors using Puppeteer or Playwright for real web browser rendering require at least 1024MB of memory.
    Large and complex sites like Google Maps require at least 4096MB for optimal speed and concurrency.
    Projects involving large amount of data in memory.

Maximum memory

Apify Actors are most commonly written in Node.js, which uses a single thread process. Unless you use external binaries such as the Chrome browser, Puppeteer, Playwright, or other multi-threaded libraries you will not gain more CPU power from assigning your Actor more than 4096MB of memory because Node.js cannot use more than 1 core.

In other words, giving a Cheerio-based crawler 16384MB of memory (4 CPU cores) will not improve its performance, because these crawlers cannot use more than 1 CPU core.
Multi-threaded Node.js configuration

It's possible to use multiple threads in Node.js-based Actor with some configuration. This can be useful if you need to offload a part of your workload.
Usage

When you run an Actor it generates platform usage that's charged to the user account. Platform usage comprises four main parts:

    Compute units: CPU and memory resources consumed by the Actor.
    Data transfer: The amount of data transferred between the web, Apify platform, and other external systems.
    Proxy costs: Residential or SERP proxy usage.
    Storage operations: Read, write, and other operations performed on the Key-value store, Dataset, and Request queue.

The platform usage can be represented either in raw units (e.g. gigabytes for data transfer, or number of writes for dataset operations), or in the dollar equivalents.

To view the usage of an Actor run, navigate to the Runs section and check out the Usage column.

Runs usage

For a more detailed breakdown, click on the specific run you want to examine and then on the ? icon next to the Usage label.

Actors run usage details
Usage billing elements

For technical reasons, when viewing the usage in dollars for a specific historical Actor run or build in the API or Apify Console, your current service pricing is used to compute the dollar amount. This should be used for informational purposes only.

For detailed information, FAQ, and, pricing check out the platform pricing page.
What is a compute unit

A compute unit (CU) is the unit of measurement for the resources consumed by Actor runs and builds. You are charged for using Actors based on CU consumption.

For example, running an Actor with1024MB of allocated memory for 1 hour will consume 1 CU. The cost of this CU depends on your subscription plan.

You can check each Actor run's exact CU usage in the run's details.

An Actor run&#39;s platform usage

You can find a summary of your overall platform and CU usage in the Billing section of Apify Console.
Compute unit calculation

CUs are calculated by multiplying two factors:

    Memory (MB) - The size of the allocated server for your Actor or task run.
    Duration (hours) - The duration for which the server is used (Actor or task run). For example, if your run took 6 minutes, you would use 0.1 (hours) as the second number to calculate CUs. The minimum granularity is a second.

Example: 1024MB memory x 1 hour = 1 CU
What determines consumption

The factors that influence resource consumption, in order of importance, are:

    Browser vs. Plain HTTP: Launching a browser (e.g., Puppeteer/Playwright) is resource-intensive and slower compared to working with plain HTML (Cheerio). Using Cheerio can be up to 20 times faster.

    Run size and frequency: Large runs can use full resource scaling and are not subjected to repeated Actor start-ups (as opposed to many short runs). Whenever possible, opt for larger batches.

    Page type: Heavy pages, such as Amazon or Facebook will take more time to load regardless whether you use a browser or Cheerio. Large pages can take up to 3 times more resources to load and parse than average pages.

You can check out our article on estimating consumption for more details on what determines consumption.


Permissions

Copy for LLM

When you run an Actor, it runs under your Apify account and may need access to your data to complete its task. Actor permissions define how much data the Actor can access. Each Actor declares its required permission level in its configuration, and the platform enforces this level at runtime.
Understanding Actor permissions

The approach is similar to mobile platforms (Android, iOS) where each app explicitly requests the access it needs and the user approves it. The difference is that instead of granular per-Actor permissions, we use two broad permission levels which cover the vast majority of use cases. If you are a developer, see the development guide on Actor permissions to learn how to declare and manage permissions for your Actors.

The permissions model follows the principle of least privilege. Actors run only with the access they explicitly request, giving you transparency and control over what the Actor can access in their account.

There are two permission levels:

    Limited permissions (default): Actors with this permission level have restricted access, primarily to their own storages, the data they generate, and resources they are given an explicit access to. They cannot access any other data in your Apify account.
    Full permissions: Grants the Actor access to all data in your Apify account.

This model protects your data and strengthens platform security by clearly showing what level of access each Actor requires.

Actors using Limited permissions are safer to run and suit most tasks. Actors that need full permissions (for example to perform administrative tasks in your account, manage your datasets or schedules) clearly indicate this in their detail page.
How Actor permissions work

When a user runs an Actor, it receives an Apify API token. Traditionally, this token grants access to the user's entire Apify account via Apify API. Actors with full permissions will continue to operate this way.

Actors with limited permissions receive a restricted token. This token only allows the Actor to perform a specific set of actions, which covers the vast majority of common use cases.

A limited-permission Actor can:

    Read and write to its default storages.
    Create any additional storage, and write to that storage.
    Read and write to storages created in previous runs.
    Update the current run's status or abort the run.
    Metamorph to another Actor with limited permissions.
    Read and write to storages provided via Actor input (for example, when the user provides a dataset that the Actor should write into).
    Read basic user information from the environment (whether the user is paying, their proxy password, or public profile).
    Run any other Actor with limited permissions.

This approach ensures the Actor has everything it needs to function while protecting your data from unnecessary exposure.
Recognizing permission levels in Console and Store

When you browse Actors in Apify Console or Store, you’ll notice a small badge next to each Actor showing its permission level. Hover over the badge to see a short explanation of what access that Actor will have when it runs under your account. Here's how they appear in the Console.

Actor tasks

Copy for LLM

Actor tasks let you create multiple reusable configurations of a single Actor, adapted for specific use cases. For example, you can create one Web Scraper configuration (task) that scrapes the latest reviews from IMDb, another that scrapes nike.com for the latest sneakers, and a third that scrapes your competitor's e-shop. You can then use and reuse these configurations directly from Apify Console, Schedules, or API.

You can find all your tasks in the Apify Console.
Create

To create a task, open any Actor from Apify Store or your list of Actors in Apify Console. At the top-right section of the page, click the Save as a new task button.

Create a new Apify task
Configure

You can set up your task's input under the Input tab. A task's input configuration works just like an Actor's. After all, it's just a copy of an Actor you can pre-configure for a specific scenario. You can use either JSON or the visual input UI.

Apify task configuration

An Actors' input fields may vary depending on their purpose, but they all follow the same principle: you provide an Actor with the information it needs so it can do what you want it to do.

You can set run options such as timeout and memory in the Run options tab of the task's input configuration.
Naming

To make a task easier to identify, you can give it a name, title, and description by clicking its caption on the detail page. A task's name should be at least 3 characters long with a limit of 63 characters.
Run

Once you've configured your task, you can run it using the Start button on the top-right side of the screen.

Run an Apify task

Or using the Start button positioned following the input configuration.

Run an Apify task v2

You can also run tasks using:

    Schedules.
    Directly via the Apify API.
    The JavaScript API client.
    The Python API client.

Share

Like any other resource, you can share your Actor tasks with other Apify users via the access rights system.

Standby mode

Copy for LLM

Traditional Actors are designed to run a single job and then stop. They're mostly intended for batch jobs, such as when you need to perform a large scrape or data processing task. However, in some applications, waiting for an Actor to start is not an option. Actor Standby mode solves this problem by letting you have the Actor ready in the background, waiting for the incoming HTTP requests. In a sense, the Actor behaves like a real-time web server or standard API server.
How do I know if Standby mode is enabled

You will know that the Actor is enabled for Standby mode if you see the Standby tab on the Actor's detail page. In the tab, you will find the hostname of the server, the description of the Actor's endpoints, the parameters they accept, and what they return in the Actor README.

To use the Actor in Standby mode, you don't need to click a start button or not need to do anything else. Simply use the provided hostname and endpoint in your application, hit the API endpoint and get results.

Standby tab
How do I pass input to Actors in Standby mode

If you're using an Actor built by someone else, see its Information tab to find out how the input should be passed.

Generally speaking, Actors in Standby mode behave as standard HTTP servers. You can use any of the existing HTTP request methods like GET, POST, PUT, DELETE, etc. You can pass the input via HTTP request query string or via HTTP request body.
How do I authenticate my requests

To authenticate requests to Actor Standby, follow the same process as authenticating requests to the Apify API. You can provide your API token in one of two ways:

    Recommended: Include the token in the Authorization header of your request as Bearer <token>. This approach is recommended because it prevents your token from being logged in server logs.

    curl -H "Authorization: Bearer my_apify_token" \
      https://rag-web-browser.apify.actor/search?query=apify

    Append the token as a query parameter named token to the request URL. This approach can be useful if you cannot modify the request headers.

    https://rag-web-browser.apify.actor/search?query=apify&token=my_apify_token

tip

You can use scoped tokens to send standby requests. This is useful for allowing third-party services to interact with your Actor without granting access to your entire account.

However, restricting what an Actor can access using a scoped token is not supported when running in Standby mode.
Can I still run the Actor in normal mode

Yes, you can still modify the input and click the Start button to run the Actor in normal mode. However, note that the Standby Actor might not support this mode; the run might fail or return empty results. The normal mode is always supported in Standby Beta, even for Actors that don't handle it well. Please head to the Actor README to learn more about the capabilities of your chosen Actor.
Is there any scaling to accommodate the incoming requests

When you use the Actor in Standby mode, the system automatically scales the Actor to accommodate the incoming requests. Under the hood, the system starts new Actor runs, which you will see in the Actor runs tab, with the origin set to Standby.
What is the timeout for incoming requests

For requests sent to an Actor in Standby mode, the maximum time allowed until receiving the first response is 5 minutes. This represents the overall timeout for the operation.
What is the rate limit for incoming requests

The rate limit for incoming requests to a Standby Actor is 2000 requests per second per user account.
How do I customize Standby configuration

The Standby configuration currently consists of the following properties:

    Max requests per run - The maximum number of concurrent HTTP requests a single Standby Actor run can accept. If this limit is exceeded, the system starts a new Actor run to handle the request, which may take a few seconds.
    Desired requests per run - The number of concurrent HTTP requests a single Standby Actor run is configured to handle. If this limit is exceeded, the system preemptively starts a new Actor run to handle the additional requests.
    Memory (MB) - The amount of memory (RAM) allocated for the Actor in Standby mode, in megabytes. With more memory, the Actor can typically handle more requests in parallel, but this also increases the number of compute units consumed and the associated cost.
    Idle timeout (seconds) - If a Standby Actor run doesn’t receive any HTTP requests within this time, the system will terminate the run. When a new request arrives, the system might need to start a new Standby Actor run to handle it, which can take a few seconds. A higher idle timeout improves responsiveness but increases costs, as the Actor remains active for a longer period.
    Build - The Actor build that the runs of the Standby Actor will use. Can be either a build tag (e.g. latest.), or a build number (e.g. 0.1.2).

You can see these in the Standby tab of the Actor detail page. However, note that these properties are not configurable at the Actor level. If you wish to use the Actor-level hostname, this will always use the default configuration. To override this configuration, just create a new Task from the Actor. You can then head to the Standby tab of the created Task and modify the configuration as needed. Note that the task has a specific hostname, so make sure to use that in your application if you wish to use the custom configuration.
Are the Standby runs billed differently

No, the Standby runs are billed in the same fashion as the normal runs. However, running Actors in Standby mode might have unexpected costs, as the Actors run in the background and consume resources even when no requests are being sent until they are terminated after the idle timeout period.
Are the Standby runs shared among users

No, even if you use the Actor-level hostname with the default configuration, the background Actor runs for your requests are not shared with other users.
How can I develop Actors using Standby mode

See the Actor Standby development section.

Build Actors with AI

Copy for LLM

This guide provides best practices for building new Actors or improving existing ones using AI code generation tools by providing the AI agents with the right instructions and context.

The methods on this page are complementary. Start with the AI coding assistant instructions or Actor templates with AGENTS.md to get going, then add Agent Skills and the Apify MCP server to give your assistant more context and better results.
Quick start

    Start with a prompt
    Start with a template

    Create a directory: mkdir my-new-actor.
    Open the directory in Cursor, Claude Code, VS Code with GitHub Copilot, etc.
    Copy the AI coding assistant prompt and paste it into your AI coding assistant.
    Run it, and develop your first Actor with the help of AI.

AI coding assistant instructions

Use the following prompt in your AI coding assistant such as Cursor, Claude Code, or GitHub Copilot:
Use pre-built prompt for your AI coding assistant

The prompt guides your AI coding assistant to create and deploy an Apify Actor step by step. It walks through setting up the Actor structure, configuring all required files, installing dependencies, running it locally, logging in, and pushing it to the Apify platform.
Use Actor templates with AGENTS.md

All Actor Templates have AGENTS.md that will help you with AI coding. You can use the Apify CLI to create Actors from Actor Templates.

apify create

If you do not have the Apify CLI installed, see the installation guide.

The command above will guide you through Apify Actor initialization, where you select an Actor Template that works for you. The result is an initialized Actor (with AGENTS.md) ready for development.
Use Agent Skills

Agent Skills are official Apify skills for Actor development, web scraping, data extraction, automation, etc. They work with Claude Code, Cursor, Codex, Gemini CLI, and other AI coding assistants.

Install Agent Skills in your project directory:

npx skills add apify/agent-skills

This adds skill files to your project that AI coding assistants automatically discover and use for context. No additional configuration is needed.
Use Apify MCP server

The Apify MCP server has tools to search and fetch documentation. If you set it up in your AI editor, it will help you improve the generated code by providing additional context to the AI.
Use Apify MCP server configuration

We have prepared the Apify MCP server configuration, which you can configure for your needs.

    Cursor
    VS Code
    Claude Code

To add Apify MCP server to Cursor manually:

    Create or open the .cursor/mcp.json file.

    Add the following to the configuration file:

    {
      "mcpServers": {
        "apify": {
          "url": "https://mcp.apify.com/?tools=docs"
        }
      }
    }

Provide context to assistants

Every page in the Apify documentation has a Copy for LLM button. You can use it to add additional context to your AI assistant, or even open the page in ChatGPT, Claude, or Perplexity and ask additional questions.
Copy for LLM
Use /llms.txt files

The entire Apify documentation is available in Markdown format for use with LLMs and AI coding tools. Two consolidated files are available:

    https://docs.apify.com/llms.txt: A Markdown file with an index of all documentation pages in Markdown format, based on the llmstxt.org standard.
    https://docs.apify.com/llms-full.txt: All Apify documentation consolidated in a single Markdown file.

Access Markdown source

Add .md to any documentation page URL to view its Markdown source.

Example: https://docs.apify.com/platform/actors > https://docs.apify.com/platform/actors.md
Provide link to AI assistants

LLMs don't automatically discover llms.txt files, you need to add the link manually to improve the quality of answers.
Best practices

    Small tasks: Don't ask AI for many tasks at once. Break complex problems into smaller pieces. Solve them step by step.

    Iterative approach: Work iteratively with clear steps. Start with a basic implementation and gradually add complexity.

    Versioning: Version your changes often using git. This lets you track changes, roll back if needed, and maintain a clear history.

    Security: Don't expose API keys, secrets, or sensitive information in your code or conversations with LLM assistants.
Local Actor development

Copy for LLM
Use pre-built prompt to get started faster.
What you'll learn

This guide walks you through the full lifecycle of an Actor. You'll start by creating and running it locally with the Apify CLI, then learn to configure its input and data storage. Finally, you will deploy the Actor to the Apify platform, making it ready to run in the cloud.
Prerequisites

    Node.js version 16 or higher with npm installed on your computer.
    The Apify CLI installed.
    Optional: To deploy your Actor, sign in.

Step 1: Create your Actor

Use the Apify CLI to create a new Actor:

apify create

The CLI will ask you to:

    Name your Actor (e.g., your-actor-name)

    Choose a programming language (JavaScript, TypeScript, or Python)

    Select a development template
    Explore Actor templates

    Browse the full list of templates to find the best fit for your Actor.

The CLI will:

    Create a your-actor-name directory with boilerplate code
    Install all project dependencies

Now, you can navigate to your new Actor directory:

cd `your-actor-name`

Step 2: Run your Actor

Run your Actor with:

apify run

You'll see output similar to this in your terminal:

INFO  System info {"apifyVersion":"3.4.3","apifyClientVersion":"2.12.6","crawleeVersion":"3.13.10","osType":"Darwin","nodeVersion":"v22.17.0"}
Extracted heading { level: 'h1', text: 'Your full‑stack platform for web scraping' }
Extracted heading { level: 'h3', text: 'TikTok Scraper' }
Extracted heading { level: 'h3', text: 'Google Maps Scraper' }
Extracted heading { level: 'h3', text: 'Instagram Scraper' }

As you can see in the logs, the Actor extracts text from a web page. The main logic lives in src/main.js. Depending on your template, this file may be src/main.ts (TypeScript) or src/main.py (Python).

In the next step, we’ll explore the results in more detail.
Step 3: Explore the Actor

Let's explore the Actor structure.
The .actor folder

The .actor folder contains the Actor configuration. The actor.json file defines the Actor's name, description, and other settings. Find more info in the actor.json definition.
Actor's input

Each Actor accepts an input object that tells it what to do. The object uses JSON format and lives in storage/key_value_stores/default/INPUT.json.
Edit the schema to change input

To change the INPUT.json, edit the input_schema.json in the .actor folder first.

This JSON Schema validates input automatically (no error handling needed), powers the Actor's user interface, generates API docs, and enables smart integration with tools like Zapier or Make by auto-linking input fields.

Find more info in the Input schema documentation.
Actor's storage

The Actor system provides two storage types for files and results: key-value store and dataset.
Key-value store

The key-value store saves and reads files or data records. Key-value stores work well for screenshots, PDFs, or persisting Actor state as JSON files.
Dataset

The dataset stores a series of data objects from web scraping, crawling, or data processing jobs. You can export datasets to JSON, CSV, XML, RSS, Excel, or HTML formats.
Actor's output

You define the Actor output using the Output schema files:

    Dataset Schema Specification
    Key-value Store Schema Specification

The system uses this to generate an immutable JSON file that tells users where to find the Actor's results.
Step 4: Deploy your Actor

Let's now deploy your Actor to the Apify platform, where you can run the Actor on a scheduled basis, or you can make the Actor public for other users.

    Login first:

    apify login

    Your Apify token location

    After you successfully login, your Apify token is stored in ~/.apify/auth.json, or C:\Users\<name>\.apify based on your system.

    Push your Actor to the Apify platform:

    apify push

Step 5: It's time to iterate!

Good job! 🎉 You're ready to develop your Actor. You can make changes to your Actor and implement your use case.
Next steps

    Visit the Apify Academy to access a comprehensive collection of tutorials, documentation, and learning resources.
    To understand Actors in detail, read the Actor Whitepaper.
    Check Continuous integration documentation to automate your Actor development process.
    After you finish building your first Actor, you can share it with other users and even monetize it.

Edit this page
Web IDE

Copy for LLM
What you'll learn

This guide walks you through the full lifecycle of an Actor using the web IDE in Apify Console. You'll create an Actor from a code template, build it, configure its input, and run it in the cloud.
Prerequisites

    An Apify account. Sign up for a free account on the Apify website.

Step 1: Create your Actor

Log in to Apify Console, navigate to My Actors, then click the Develop new button. You can also click the Create button on the Dashboard and select Create Actor.

Create Actor

You'll see options to link a Git repository, select a code template, or push code with the Apify CLI.

Under Select a code template, you'll find quick-start templates for TypeScript, Python, and JavaScript. Click Browse all templates to see the full list. Choose the template that best suits your needs. For the following demo, we'll proceed with a Crawlee + Cheerio template.
Explore Actor templates

Browse the full list of templates to find the best fit for your Actor.

Templates

After choosing the template, your Actor will be automatically named and you'll be redirected to its page.
Step 2: Explore the Actor

The provided boilerplate code utilizes the Apify SDK combined with Crawlee, Apify's popular open-source Node.js web scraping library.

By default, the code crawls the apify.com website, but you can change it to any website.
Crawlee

Crawlee is an open-source Node.js library designed for web scraping and browser automation. It helps you build reliable crawlers quickly and efficiently.
Step 3: Build the Actor

To run your Actor, build it first. Click the Build button below the source code.

Actor source code

Once the build starts, the UI transitions to the Last build tab, showing build progress and Docker build logs.

Actor build
Actor creation flow

The UI includes four tabs:

    Code
    Last build
    Input
    Last run

This represents the Actor creation flow, where you first build the Actor from the source code. Once the build is successful, you can provide input parameters and initiate an Actor run.
Step 4: Run the Actor

Once the Actor is built, you can look at its input, which consists of one field - Start URL, the URL where the crawling starts. Below the input, you can adjust the Run options:

    Build
    Timeout
    Memory limit

Actor input

To initiate an Actor run, click the Start button at the bottom of the page. Once the run is created, you can monitor its progress and view the log in real-time. The Output tab will display the results of the Actor's execution, which will be populated as the run progresses. You can abort the run at any time using the Abort button.

Actor run
Step 5: Pull the Actor

To continue development locally, pull the Actor's source code to your machine.
Prerequisites

Install apify-cli :

    macOS/Linux
    Other platforms

brew install apify-cli

To pull your Actor:

    Log in to the Apify platform

    apify login

    Pull your Actor:

    apify pull your-actor-name

    Or with a specific version:

    apify pull your-actor-name --version [version_number]

    As your-actor-name, you can use either:
        The unique name of the Actor (e.g., apify/hello-world)
        The ID of the Actor (e.g., E2jjCZBezvAZnX8Rb)

You can find both by clicking on the Actor title at the top of the page, which will open a new window containing the Actor's unique name and ID.
Step 6: It's time to iterate!

After pulling the Actor's source code to your local machine, you can modify and customize it to match your specific requirements. Leverage your preferred code editor or development environment to make the necessary changes and enhancements.

Once you've made the desired changes, you can push the updated code back to the Apify platform for deployment & execution, leveraging the platform's scalability and reliability.
Next steps

    Visit the Apify Academy to access a comprehensive collection of tutorials, documentation, and learning resources.
    To understand Actors in detail, read the Actor Whitepaper.
    Check Continuous integration documentation to automate your Actor development process.
    After you finish building your first Actor, you can share it with other users and even monetize it.

Edit this page

actor.json

Copy for LLM

Your main Actor configuration is in the .actor/actor.json file at the root of your Actor's directory. This file links your local development project to an Actor on the Apify platform. It should include details like the Actor's name, version, build tag, and environment variables. Make sure to commit this file to your Git repository.

For example, the .actor/actor.json file can look like this:

    Full actor.json
    Minimal actor.json

{
    "actorSpecification": 1, // always 1
    "name": "name-of-my-scraper",
    "title": "My Web Scraper",
    "version": "0.0",
    "buildTag": "latest",
    "meta": {
        "templateId": "ts-crawlee-playwright-chrome"
    },
    "defaultMemoryMbytes": "get(input, 'startUrls.length', 1) * 1024",
    "minMemoryMbytes": 256,
    "maxMemoryMbytes": 4096,
    "environmentVariables": {
        "MYSQL_USER": "my_username",
        "MYSQL_PASSWORD": "@mySecretPassword"
    },
    "usesStandbyMode": false,
    "dockerfile": "./Dockerfile",
    "readme": "./ACTOR.md",
    "input": "./input_schema.json",
    "storages": {
        "dataset": "./dataset_schema.json"
    },
    "webServerSchema": "./web_server_openapi.json",
    "webServerMcpPath": "/mcp"
}

Reference
Deployment metadata

Actor name, version, buildTag, and environmentVariables are currently only used when you deploy your Actor using the Apify CLI and not when deployed, for example, via GitHub integration. There, it serves for informative purposes only.
Property	Type	Description
actorSpecification	Required	The version of the Actor specification. This property must be set to 1, which is the only version available.
name	Required	The name of the Actor.
title	Optional	The display title of the Actor. This is the human-readable title shown in Apify Console and Apify Store. If not specified, the name property is used as the title.
version	Required	The version of the Actor, specified in the format [Number].[Number], e.g., 0.1, 0.3, 1.0, 1.3, etc.
buildTag	Optional	The tag name to be applied to a successful build of the Actor. If not specified, defaults to latest. Refer to the builds for more information.
meta	Optional	Metadata object containing additional information about the Actor. Currently supports templateId field to identify the template from which the Actor was created.
environmentVariables	Optional	A map of environment variables to be used during local development. These variables will also be applied to the Actor when deployed on the Apify platform. For more details, see the environment variables section of the Apify CLI documentation.
dockerfile	Optional	The path to the Dockerfile to be used for building the Actor on the platform. If not specified, the system will search for Dockerfiles in the .actor/Dockerfile and Dockerfile paths, in that order. Refer to the Dockerfile section for more information.
dockerContextDir	Optional	The path to the directory to be used as the Docker context when building the Actor. The path is relative to the location of the actor.json file. This property is useful for monorepos containing multiple Actors. Refer to the Actor monorepos section for more details.
readme	Optional	The path to the README file to be used on the platform. If not specified, the system will look for README files in the .actor/README.md and README.md paths, in that order of preference. Check out Apify Marketing Playbook to learn how to write a quality README files guidance.
input	Optional	You can embed your input schema object directly in actor.json under the input field. You can also provide a path to a custom input schema. If not provided, the input schema at .actor/INPUT_SCHEMA.json or INPUT_SCHEMA.json is used, in this order of preference.
changelog	Optional	The path to the CHANGELOG file displayed in the Information tab of the Actor in Apify Console next to Readme. If not provided, the CHANGELOG at .actor/CHANGELOG.md or CHANGELOG.md is used, in this order of preference. Your Actor doesn't need to have a CHANGELOG but it is a good practice to keep it updated for published Actors.
storages.dataset	Optional	You can define the schema of the items in your dataset under the storages.dataset field. This can be either an embedded object or a path to a JSON schema file. Read more about Actor dataset schemas.
storages.datasets	Optional	You can define multiple datasets for the Actor under the storages.datasets field. This can be an object containing embedded objects or paths to a JSON schema files. Read more about multiple dataset schemas.
defaultMemoryMbytes	Optional	Specifies the default amount of memory in megabytes to be used when the Actor is started. Can be an integer or a dynamic memory expression string.
minMemoryMbytes	Optional	Specifies the minimum amount of memory in megabytes required by the Actor to run. Requires an integer value. If both minMemoryMbytes and maxMemoryMbytes are set, then minMemoryMbytes must be equal or lower than maxMemoryMbytes. Refer to the Usage and resources for more details about memory allocation.
maxMemoryMbytes	Optional	Specifies the maximum amount of memory in megabytes required by the Actor to run. It can be used to control the costs of run. Requires an integer value. Refer to the Usage and resources for more details about memory allocation.
usesStandbyMode	Optional	Boolean specifying whether the Actor will have Standby mode enabled.
webServerSchema	Optional	Defines an OpenAPI v3 schema for the web server running in the Actor. This can be either an embedded object or a path to a JSON schema file. Use this when your Actor starts its own HTTP server and you want to describe its interface.
webServerMcpPath	Optional	The HTTP endpoint path where the Actor exposes its MCP (Model Context Protocol) server functionality. When set, the Actor is recognized as an MCP server. For example, setting "/mcp" designates the /mcp endpoint as the MCP interface. This path becomes part of the Actor's stable URL when Standby mode is enabled.
Source code

Copy for LLM

The Apify Actor's source code placement is defined by its Dockerfile. If you have created the Actor from one of Apify's templates then it's by convention placed in the /src directory.

You have the flexibility to choose any programming language, technologies, and dependencies (such as Chrome browser, Selenium, Cypress, or others) for your projects. The only requirement is to define a Dockerfile that builds the image for your Actor, including all dependencies and your source code.
Example setup

Let's take a look at the example JavaScript Actor's source code. The following Dockerfile:

FROM apify/actor-node:20

COPY package*.json ./

RUN npm --quiet set progress=false \
    && npm install --omit=dev --omit=optional \
    && echo "Installed NPM packages:" \
    && (npm list --omit=dev --all || true) \
    && echo "Node.js version:" \
    && node --version \
    && echo "NPM version:" \
    && npm --version \
    && rm -r ~/.npm

COPY . ./

CMD npm start --silent

This Dockerfile does the following tasks:

    Builds the Actor from the apify/actor-node:20 base image.

    FROM apify/actor-node:20

    Copies the package.json and package-lock.json files to the image.

    COPY package*.json ./

    Installs the npm packages specified in package.json, omitting development and optional dependencies.

    RUN npm --quiet set progress=false \
        && npm install --omit=dev --omit=optional \
        && echo "Installed NPM packages:" \
        && (npm list --omit=dev --all || true) \
        && echo "Node.js version:" \
        && node --version \
        && echo "NPM version:" \
        && npm --version \
        && rm -r ~/.npm

    Copies the rest of the source code to the image

    COPY . ./

    Runs the npm start command defined in package.json

    CMD npm start --silent

Optimized build cache

By copying the package.json and package-lock.json files and installing dependencies before the rest of the source code, you can take advantage of Docker's caching mechanism. This approach ensures that dependencies are only reinstalled when the package.json or package-lock.json files change, significantly reducing build times. Since the installation of dependencies is often the most time-consuming part of the build process, this optimization can lead to substantial performance improvements, especially for larger projects with many dependencies.
package.json

The package.json file defines the npm start command:

{
    "name": "getting-started-node",
    "version": "0.0.1",
    "type": "module",
    "description": "This is an example of an Apify Actor.",
    "dependencies": {
        "apify": "^3.0.0"
    },
    "devDependencies": {},
    "scripts": {
        "start": "node src/main.js",
        "test": "echo \"Error: oops, the Actor has no tests yet, sad!\" && exit 1"
    },
    "author": "It's not you; it's me",
    "license": "ISC"
}

When the Actor starts, the src/main.js file is executed.

Actor input schema specification

Copy for LLM

Actor input schema is a JSON file which defines the schema and description of the input object and its properties accepted by the Actor on start. The file adheres to JSON schema with our extensions, and describes a single Actor input object and its properties, including documentation, default value, and user interface definition.

The Actor input schema file is used to:

    Validate the passed input JSON object on Actor run, so that Actors don't need to perform input validation and error handling in their code.
    Render user interface for Actors to make it easy for users to run and test them manually.
    Generate Actor API documentation and integration code examples on the web or in CLI, making Actors easy to integrate for users.
    Simplify integration of Actors into automation workflows such as Zapier or Make, by providing smart connectors that smartly pre-populate and link Actor input properties.

To define an input schema for an Actor, set input field in the .actor/actor.json file to an input schema object (described below), or path to a JSON file containing the input schema object. For backwards compatibility, if the input field is omitted, the system looks for an INPUT_SCHEMA.json file either in the .actor directory or the Actor's top-level directory - but note that this functionality is deprecated and might be removed in the future. The maximum allowed size for the input schema file is 500 kB.

When you provide an input schema, the Apify platform will validate the input data passed to the Actor on start (via the API or Apify Console) to ensure compliance before starting the Actor. If the input object doesn't conform the schema, the caller receives an error and the Actor is not started.
Validation aid

You can use our visual input schema editor to guide you through the creation of the INPUT_SCHEMA.json file.

To ensure the input schema is valid, here's a corresponding JSON schema file.

You can also use the apify validate-schema command in the Apify CLI.
Example

Imagine a simple web crawler that accepts an array of start URLs and a JavaScript function to execute on each visited page. The input schema for such a crawler could be defined as follows:

{
    "title": "Cheerio Crawler input",
    "description": "To update crawler to another site, you need to change startUrls and pageFunction options!",
    "type": "object",
    "schemaVersion": 1,
    "properties": {
        "startUrls": {
            "title": "Start URLs",
            "type": "array",
            "description": "URLs to start with",
            "prefill": [
                { "url": "http://example.com" },
                { "url": "http://example.com/some-path" }
            ],
            "editor": "requestListSources"
        },
        "pageFunction": {
            "title": "Page function",
            "type": "string",
            "description": "Function executed for each request",
            "prefill": "async () => { return $('title').text(); }",
            "editor": "javascript"
        }
    },
    "required": ["startUrls", "pageFunction"]
}

The generated input UI will be:

Apify Actor input schema example

If you switch the input to the JSON display using the toggle, then you will see the entered input stringified to JSON, as it will be passed to the Actor:

{
    "startUrls": [
    {
        "url": "http://example.com"
    },
    {
        "url": "http://example.com/some-path"
    }
    ],
    "pageFunction": "async () => { return $('title').text(); }"
}

Structure

{
    "title": "Cheerio Crawler input",
    "type": "object",
    "schemaVersion": 1,
    "properties": { /* define input fields here */ },
    "required": []
}

Property	Type	Required	Description
title	String	Yes	Any text describing your input schema.
description	String	No	Help text for the input that will be
displayed above the UI fields.
type	String	Yes	This is fixed and must be set
to string object.
schemaVersion	Integer	Yes	The version of the input schema
specification against which
your schema is written.
Currently, only version 1 is out.
properties	Object	Yes	This is an object mapping each field key
to its specification.
required	String	No	An array of field keys that are required.
additionalProperties	Boolean	No	Controls if properties not listed in properties are allowed. Defaults to true.
Set to false to make requests with extra properties fail.
Input schema differences

Even though the structure of the Actor input schema is similar to JSON schema, there are some differences. We cannot guarantee that JSON schema tooling will work on input schema documents. For a more precise technical understanding of the matter, feel free to browse the code of the @apify/input_schema package.
Input fields

Each field of your input is described under its key in the inputSchema.properties object. The field might have integer, string, array, object, or boolean type, and its specification contains the following properties:
Property	Value	Required	Description
type	One of

    string
    array
    object
    boolean
    integer

	Yes	Allowed type for the input value.
Cannot be mixed.
title	String	Yes	Title of the field in UI.
description	String	Yes	Description of the field that will be
displayed as help text in Actor input UI.
default	Must match type property.	No	Default value that will be
used when no value is provided.
prefill	Must match type property.	No	Value that will be prefilled
in the Actor input interface.
example	Must match type property.	No	Sample value of this field
for the Actor to be displayed when
Actor is published in Apify Store.
errorMessage	Object	No	Custom error messages for validation keywords.
See custom error messages
for more details.
sectionCaption	String	No	If this property is set,
then all fields following this field
(this field included) will be separated
into a collapsible section
with the value set as its caption.
The section ends at the last field
or the next field which has the
sectionCaption property set.
sectionDescription	String	No	If the sectionCaption property is set,
then you can use this property to
provide additional description to the section.
The description will be visible right under
the caption when the section is open.
Prefill vs. default vs. required

Here is a rule of thumb for whether an input field should have a prefill, default, or be required:

    Prefill - Use for fields that don't have a reasonable default. The provided value is prefilled for the user to show them an example of using the field and to make it easy to test the Actor (e.g., search keyword, start URLs). In other words, this field is only used in the user interface but does not affect the Actor functionality and API. Note that if you add a new input option to your Actor, the Prefill value won't be used by existing integrations such as Actor tasks or API calls, but the Default will be if specified. This is useful for keeping backward compatibility when introducing a new flag or feature that you prefer new users to use.
    Required - Use for fields that don't have a reasonable default and MUST be entered by the user (e.g., API token, password).
    Default - Use for fields that MUST be set for the Actor run to some value, but where you don't need the user to change the default behavior (e.g., max pages to crawl, proxy settings). If the user omits the value when starting the Actor via any means (API, CLI, scheduler, or user interface), the platform automatically passes the Actor this default value.
    No particular setting - Use for purely optional fields where it makes no sense to prefill any value (e.g., flags like debug mode or download files).

In summary, you can use each option independently or use a combination of Prefill + Required or Prefill + Default, but the combination of Default + Required doesn't make sense to use.
Input types

Most types also support additional properties defining, for example, the UI input editor.
String

String is the most common input field type, and provide a number of editors and validations properties:
Property	Value	Required	Description
editor	One of:
- textfield
- textarea
- javascript
- python
- select
- datepicker
- fileupload
- hidden	Yes	Visual editor used for the input field.
pattern	String	No	Regular expression that will be used to validate the input. If validation fails, the Actor will not run.
minLength	Integer	No	Minimum length of the string.
maxLength	Integer	No	Maximum length of the string.
enum	[String]	Required if editor is select	Using this field, you can limit values to the given array of strings. Input will be displayed as select box. Values are strictly validated against this list.
enumSuggestedValues	[String]	No	Similar to enum, but only suggests values in the UI without enforcing validation. Users can select from the dropdown or enter custom value.
Works only with the select editor.
enumTitles	[String]	No	Displayed titles for the enum or enumSuggestedValues properties.
nullable	Boolean	No	Specifies whether null is an allowed value.
isSecret	Boolean	No	Specifies whether the input field will be stored encrypted. Only available with textfield, textarea and hidden editors.
dateType	One of

    absolute
    relative
    absoluteOrRelative

	No	This property, which is only available with datepicker editor, specifies what date format should visual editor accept (The JSON editor accepts any string without validation.).

    absolute value enables date input in YYYY-MM-DD format. To parse returned string regex like this can be used: ^(\d{4})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$.

    relative value enables relative date input in
    {number} {unit} format.
    Supported units are: days, weeks, months, years.

    The input is passed to the Actor as plain text (e.g., "3 weeks"). To parse it, regex like this can be used: ^(\d+)\s*(day|week|month|year)s?$.

    absoluteOrRelative value enables both absolute and relative formats and user can switch between them. It's up to Actor author to parse a determine actual used format - regexes above can be used to check whether the returned string match one of them.


Defaults to absolute.
Regex escape

When using escape characters \ for the regular expression in the pattern field, be sure to escape them to avoid invalid JSON issues. For example, the regular expression https:\/\/(www\.)?apify\.com\/.+ would become https:\\/\\/(www\\.)?apify\\.com\\/.+.
Select editor for strings

The select editor for strings allows users to choose a value from a dropdown list. You can either only allow users to select from a set of predefined values, or allow them to specify custom values in addition to suggested values.
Select from predefined values

When you need to restrict input to a specific set of values, use the enum property:

{
    "title": "Country",
    "type": "string",
    "description": "Select your country",
    "editor": "select",
    "default": "us",
    "enum": ["us", "de", "fr"],
    "enumTitles": ["USA", "Germany", "France"]
}

The select editor is rendered as drop-down in user interface:

Apify Actor input schema - country input
Select with custom input

When you want to suggest values but still allow custom input, use the enumSuggestedValues property:

{
    "title": "Tag",
    "type": "string",
    "description": "Select or enter a custom tag",
    "editor": "select",
    "default": "web",
    "enumSuggestedValues": ["web", "scraping", "automation"],
    "enumTitles": ["Web", "Scraping", "Automation"]
}

This creates a select dropdown with suggested values, but users can also enter custom values:

Apify Actor input schema - tag input suggestion
Code editor

If the input string is code, you can use either javascript or python editor for syntax highlighting.

For example:

{
    "title": "Page function",
    "type": "string",
    "description": "Function executed for each request",
    "editor": "javascript",
    "prefill": "async () => { return $('title').text(); }"
}

Rendered input:

Apify Actor input schema page function
Date picker

Example of date selection using absolute and relative datepicker editor:

{
    "absoluteDate": {
        "title": "Date",
        "type": "string",
        "description": "Select absolute date in format YYYY-MM-DD",
        "editor": "datepicker",
        "pattern": "^(\\d{4})-(0[1-9]|1[0-2])-(0[1-9]|[12]\\d|3[01])$"
    },
    "relativeDate": {
        "title": "Relative date",
        "type": "string",
        "description": "Select relative date in format: {number} {unit}",
        "editor": "datepicker",
        "dateType": "relative",
        "pattern": "^(\\d+)\\s*(day|week|month|year)s?$"
    },
    "anyDate": {
        "title": "Any date",
        "type": "string",
        "description": "Select date in format YYYY-MM-DD or {number} {unit}",
        "editor": "datepicker",
        "dateType": "absoluteOrRelative",
        "pattern": "^(\\d{4})-(0[1-9]|1[0-2])-(0[1-9]|[12]\\d|3[01])$|^(\\d+)\\s*(day|week|month|year)s?$"
    }
}

The absoluteDate property renders a date picker that allows selection of a specific date and returns string value in YYYY-MM-DD format. Validation is ensured thanks to pattern field. In this case the dateType property is omitted, as it defaults to "absolute".

Apify Actor input schema - country input

The relativeDate property renders an input field that enables the user to choose the relative date and returns the value in {number} {unit} format, for example "2 days". The dateType parameter is set to "relative" to restrict input to relative dates only.

Apify Actor input schema - country input

The anyDate property renders a date picker that accepts both absolute and relative dates. The Actor author is responsible for parsing and interpreting the selected date format.

Apify Actor input schema - country input
Advanced date and time handling

While the datepicker editor doesn't support setting time values visually, you can allow users to handle more complex datetime formats and pass them via JSON. The following regex allows users to optionally extend the date with full ISO datetime format or pass hours and minutes as a relative date:

"pattern": "^(\\d{4})-(0[1-9]|1[0-2])-(0[1-9]|[12]\\d|3[01])(T[0-2]\\d:[0-5]\\d(:[0-5]\\d)?(\\.\\d+)?Z?)?$|^(\\d+)\\s*(minute|hour|day|week|month|year)s?$"

When implementing time-based fields, make sure to explain to your users through the description that the time values should be provided in UTC. This helps prevent timezone-related issues.
File upload

The fileupload editor enables users to specify a file as input. The input is passed to the Actor as a string. It is the Actor author's responsibility to interpret this string, including validating its existence and format.

The editor makes it easier to users to upload the file to a key-value store of their choice.

Apify Actor input schema - fileupload input

The user provides either a URL or uploads the file to a key-value store (existing or new).

Apify Actor input schema - fileupload input options
Boolean type

Example options with group caption:

{
    "verboseLog": {
        "title": "Verbose log",
        "type": "boolean",
        "description": "Debug messages will be included in the log.",
        "default": true,
        "groupCaption": "Options",
        "groupDescription": "Various options for this Actor"
    },
    "lightspeed": {
        "title": "Lightspeed",
        "type": "boolean",
        "description": "If checked then actors runs at the
            speed of light.",
        "prefill": true
    }
}

Rendered input:

Apify Actor input schema options

Properties:
Property	Value	Required	Description
editor	One of

    checkbox
    hidden

	No	Visual editor used for the input field.
groupCaption	String	No	If you want to group
multiple checkboxes together,
add this option to the first
of the group.
groupDescription	String	No	Description displayed as help text
displayed of group title.
nullable	Boolean	No	Specifies whether null is
an allowed value.
Numeric types

There are two numeric types supported in the input schema: integer and number.

    The integer type represents whole numbers.
    The number type can represent both integers and floating-point numbers.

Example:

{
    "title": "Memory",
    "type": "integer",
    "description": "Select memory in megabytes",
    "default": 64,
    "maximum": 1024,
    "unit": "MB"
}

Rendered input:

Apify Actor input schema memory

Properties:
Property	Value	Required	Description
type	One of

    integer
    number

	Yes	Defines the type of the field - either an integer or a floating-point number.
editor	One of:

    number
    hidden

	No	Visual editor used for input field.
maximum	Integer or Number
(based on the type)	No	Maximum allowed value.
minimum	Integer or Number
(based on the type)	No	Minimum allowed value.
unit	String	No	Unit displayed next to the field in UI,
for example second, MB, etc.
nullable	Boolean	No	Specifies whether null is an allowed value.
Object type

Example of proxy configuration:

{
    "title": "Proxy configuration",
    "type": "object",
    "description": "Select proxies to be used by your crawler.",
    "prefill": { "useApifyProxy": true },
    "editor": "proxy"
}

Rendered input:

Apify Actor input schema proxy

The object where the proxy configuration is stored has the following structure:

{
    // Indicates whether Apify Proxy was selected.
    "useApifyProxy": Boolean,

    // Array of Apify Proxy groups. Is missing or null if
    // Apify Proxy's automatic mode was selected
    // or if proxies are not used.
    "apifyProxyGroups": String[],

    // Array of custom proxy URLs.
    // Is missing or null if custom proxies were not used.
    "proxyUrls": String[],
}

Example of a black box object:

{
    "title": "User object",
    "type": "object",
    "description": "Enter object representing user",
    "prefill": {
        "name": "John Doe",
        "email": "janedoe@gmail.com"
    },
    "editor": "json"
}

Rendered input:

Apify Actor input schema user object

Properties:
Property	Value	Required	Description
editor	One of

    json
    proxy
    schemaBased
    hidden

	Yes	UI editor used for input.
maxProperties	Integer	No	Maximum number of properties
the object can have.
minProperties	Integer	No	Minimum number of properties
the object can have.
nullable	Boolean	No	Specifies whether null is
an allowed value.
isSecret	Boolean	No	Specifies whether the input field will be stored encrypted. Only available with json and hidden editors.
properties	Object	No	Defines the sub-schema properties for the object used for validation and UI rendering (schemaBased editor). See more info below.
additionalProperties	Boolean	No	Controls if sub-properties not listed in properties are allowed. Defaults to true. Set to false to make requests with extra properties fail.
required	String array	No	An array of sub-properties keys that are required.
Note: This applies only if the object field itself is present. If the object field is optional and not included in the input, its required subfields are not validated.
patternKey	String	No	Deprecated (see migration information).
Regular expression that will be used to validate the keys of the object.
patternValue	String	No	Deprecated (see migration information).
Regular expression that will be used to validate the values of object.
Object fields validation

Like root-level input schemas, you can define a schema for sub-properties of an object using the properties field.

Each sub-property within this sub-schema can define the same fields as those available at the root level of the input schema, except for the fields that apply only at the root level: sectionCaption and sectionDescription.

Validation is performed both in the UI and during Actor execution via the API. Sub-schema validation works independently of the editor selected for the parent object. It also respects the additionalProperties and required fields, giving you precise control over whether properties not defined in properties are permitted and which properties are mandatory.
Recursive nesting

Object sub-properties can define their own sub-schemas recursively with no nesting depth limit.
Example of an object property with sub-schema properties

{
    "title": "Configuration",
    "type": "object",
    "description": "Advanced configuration options",
    "editor": "json",
    "properties": {
        "locale": {
            "title": "Locale",
            "type": "string",
            "description": "Locale identifier.",
            "pattern": "^[a-z]{2,3}-[A-Z]{2}$"
        },
        "timeout": {
            "title": "Timeout",
            "type": "integer",
            "description": "Request timeout in seconds",
            "minimum": 1,
            "maximum": 300
        },
        "debugMode": {
            "title": "Debug Mode",
            "type": "boolean",
            "description": "Enable verbose logging during scraping"
        }
    },
    "required": ["locale", "timeout"],
    "additionalProperties": false
}

Rendered input: Apify Actor input schema with sub-schema

In this example, the object has validation rules for its properties:

    The timeout property must be an integer between 1 and 300
    The locale property must be a string matching the pattern ^[a-z]{2,3}-[A-Z]{2}$
    The debugMode property is optional and can be either true or false
    The timeout and locale properties are required
    No additional properties beyond those defined are allowed

Handling default and prefill values for object sub-properties

When defining object with sub-properties, it's possible to set default and prefill values in two ways:

    At the parent object level: You can provide a complete object as the default or prefill value, which will set values for all sub-properties at once.
    At the individual sub-property level: You can specify default or prefill values for each sub-property separately within the properties definition.

When both methods are used, the values defined at the parent object level take precedence over those defined at the sub-property level. For example, in the input schema like this:

{
    "title": "Configuration",
    "type": "object",
    "description": "Advanced configuration options",
    "editor": "schemaBased",
    "default": {
        "timeout": 60
    },
    "properties": {
        "locale": {
            "title": "Locale",
            "type": "string",
            "description": "Locale identifier.",
            "pattern": "^[a-z]{2,3}-[A-Z]{2}$",
            "editor": "textfield",
            "default": "en-US"
        },
        "timeout": {
            "title": "Timeout",
            "type": "integer",
            "description": "Request timeout in seconds",
            "minimum": 1,
            "maximum": 300,
            "editor": "number",
            "default": 120
        }
    }
}

The timeout sub-property will have a default value of 60 (from the parent object), while the locale sub-property will have a default value of "en-US" (from its own definition).
Schema-based editor

Object with sub-schema defined can use the schemaBased editor, which provides a user-friendly interface for editing each property individually. It renders all properties based on their type (and editor field), providing a user-friendly interface for complex objects. This feature works for objects (and arrays of objects), enabling each property to have its own input field in the UI.

Objects with a defined sub-schema can use the schemaBased editor, which provides a user-friendly interface for editing each property individually. It renders all properties based on their type (and optionally the editor field), making it ideal for visually managing complex object structures. This editor supports both single objects and arrays of objects (see below), allowing each property to be represented with an appropriate input field in the UI.
Example of an object property with sub-schema properties using schemaBased editor

{
    "title": "Configuration",
    "type": "object",
    "description": "Advanced configuration options",
    "editor": "schemaBased",
    "properties": {
        "locale": {
            "title": "Locale",
            "type": "string",
            "description": "Locale identifier.",
            "pattern": "^[a-z]{2,3}-[A-Z]{2}$",
            "editor": "textfield"
        },
        "timeout": {
            "title": "Timeout",
            "type": "integer",
            "description": "Request timeout in seconds",
            "minimum": 1,
            "maximum": 300,
            "editor": "number"
        },
        "debugMode": {
            "title": "Debug Mode",
            "type": "boolean",
            "description": "Enable verbose logging during scraping",
            "editor": "checkbox"
        }
    },
    "required": ["locale", "timeout"],
    "additionalProperties": false
}

Rendered input: Apify Actor input schema with sub-schema editor

Each sub-property is rendered with its own input field according to its type and editor configuration:

    The locale property is rendered as a text field.
    The timeout property is rendered as a numeric input with validation limits.
    The debugMode property is rendered as a checkbox toggle.

Limitations

The schemaBased editor supports only top-level sub-properties (level 1 nesting). While deeper nested properties can still define sub-schemas for validation, they cannot use the schemaBased editor for rendering. For example, if the Configuration object above included a property that was itself an object with its own sub-properties, those deeper levels would need to use a different editor, such as json.
Array

Example of request list sources configuration:

{
    "title": "Start URLs",
    "type": "array",
    "description": "URLs to start with",
    "prefill": [{ "url": "https://apify.com" }],
    "editor": "requestListSources"
}

Rendered input:

Apify Actor input schema start urls array

Example of an array:

{
    "title": "Colors",
    "type": "array",
    "description": "Enter colors you know",
    "prefill": ["Red", "White"],
    "editor": "json"
}

Rendered input:

Apify Actor input schema colors array

Properties:
Property	Value	Required	Description
editor	One of

    json
    requestListSources
    pseudoUrls
    globs
    keyValue
    stringList
    fileupload
    select
    schemaBased
    hidden

	Yes	UI editor used for input.
placeholderKey	String	No	Placeholder displayed for
key field when no value is specified.
Works only with keyValue editor.
placeholderValue	String	No	Placeholder displayed in value field
when no value is provided.
Works only with keyValue and
stringList editors.
maxItems	Integer	No	Maximum number of items
the array can contain.
minItems	Integer	No	Minimum number of items
the array can contain.
uniqueItems	Boolean	No	Specifies whether the array
should contain only unique values.
nullable	Boolean	No	Specifies whether null is
an allowed value.
items	object	No	Specifies format of the items of the array, useful mainly for multiselect and for schemaBased editor (see below).
isSecret	Boolean	No	Specifies whether the input field will be stored encrypted. Only available with json and hidden editors.
patternKey	String	No	Deprecated (see migration information).
Regular expression that will be used to validate the keys of items in the array.
Works only with keyValue
editor.
patternValue	String	No	Deprecated (see migration information).
Regular expression that will be used to validate the values of items in the array.
Works only with keyValue and
stringList editors.

Usage of this field is based on the selected editor:

    requestListSources - value from this field can be used as input for the RequestList class from Crawlee.
    pseudoUrls - is intended to be used with a combination of the PseudoUrl class and the enqueueLinks() function from Crawlee.

Editor type requestListSources supports input in formats defined by the sources property of RequestListOptions.

Editor type globs maps to the Crawlee's GlobInput used by the UrlPatterObject.

Editor type fileupload enables users to specify a list of files as input. The input is passed to the Actor as an array of strings. The Actor author is responsible for interpreting the strings, including validating file existence and format. This editor simplifies the process for users to upload files to a key-value store of their choice.
Select editor for arrays

The select editor for arrays allows users to pick multiple items from a dropdown list. This creates a multiselect field in the UI. You can either only allow users to select from a set of predefined values, or allow them to specify custom values in addition to suggested values.

To correctly define options for multiselect, you need to define the items property and then provide values in enum/enumSuggestedValues and (optionally) labels in enumTitles properties.
Select from predefined values

When you need to restrict selections to a specific set of values, use the enum property:

{
    "title": "Countries",
    "description": "Select multiple countries",
    "type": "array",
    "editor": "select",
    "items": {
        "type": "string",
        "enum": ["us", "de", "fr", "uk", "jp"],
        "enumTitles": ["United States", "Germany", "France", "United Kingdom", "Japan"]
    }
}

This creates a multiselect dropdown where users can only select from the predefined values:

Apify Actor input schema - multiselect with predefined values
Select with custom input

When you want to suggest values but still allow custom input, use the enumSuggestedValues property:

{
    "title": "Tags",
    "description": "Select or enter custom tags",
    "type": "array",
    "editor": "select",
    "items": {
        "type": "string",
        "enumSuggestedValues": ["web", "scraping", "automation", "data", "api"],
        "enumTitles": ["Web", "Scraping", "Automation", "Data", "API"]
    }
}

This creates a multiselect dropdown with suggested values, but users can also enter custom values:

Apify Actor input schema - multiselect with custom values
Array items validation

Arrays in the input schema can define an items field to specify the type and validation rules for each item. Each array item is validated according to its type and inside the items field it's also possible to define additional validation rules such as pattern, minimum, maximum, etc., depending on the item type.

If the item type is an object, it can define its own properties, required, and additionalProperties fields, working in the same way as a single object field (see Object fields validation).

Validation is performed both in the UI and during Actor execution via the API. Array items can themselves be objects with sub-schemas, and objects within objects, recursively, without any limit on nesting depth.
Example of an array of objects property with sub-schema

{
    "title": "Request Headers",
    "type": "array",
    "description": "List of custom HTTP headers",
    "editor": "json",
    "items": {
        "type": "object",
        "properties": {
            "name": {
                "title": "Header Name",
                "description": "Name of the HTTP header",
                "type": "string",
                "minLength": 1
            },
            "value": {
                "title": "Header Value",
                "description": "Value of the HTTP header",
                "type": "string",
                "minLength": 1
            }
        },
        "required": ["name", "value"],
        "additionalProperties": false
    },
    "minItems": 1,
    "maxItems": 20
}

Rendered input: Apify Actor input schema with sub-schema array

In this example:

    The array must contain between 1 and 20 items.
    Each item must be an object with name and value properties.
    Both name and value are required.
    No additional properties beyond those defined are allowed.
    The validation of each object item works the same as for a single object field (see Object fields validation).

Handling default and prefill values array with object sub-properties

When defining an array of objects with sub-properties, it's possible to set default and prefill values in two ways:

    At the parent array level: You can provide an array of complete objects as the default or prefill value, which will be used only if there is no value specified for the field.
    At the individual sub-property level: You can specify default or prefill values for each sub-property within the properties definition of the object items. These values will be applied to each object in the array value.

For example, having an input schema like this:

{
    "title": "Requests",
    "type": "array",
    "description": "List of HTTP requests",
    "editor": "schemaBased",
    "default": [
        { "url": "https://apify.com", "port": 80 }
    ],
    "items": {
        "type": "object",
        "properties": {
            "url": {
                "title": "URL",
                "type": "string",
                "description": "Request URL",
                "editor": "textfield"
            },
            "port": {
                "title": "Port",
                "type": "integer",
                "description": "Request port",
                "editor": "number",
                "default": 8080
            }
        },
        "required": ["url", "port"],
        "additionalProperties": false
    }
}

If there is no value specified for the field, the array will default to containing one object:

[
    { "url": "https://apify.com", "port": 80 }
]

However, if the user adds a new item to the array, the port sub-property of that new object will default to 8080, as defined in the sub-property itself.
schemaBased editor

Arrays can use the schemaBased editor to provide a user-friendly interface for editing each item individually. It works for arrays of primitive types (like strings or numbers) as well as arrays of objects, rendering each item according to its type and optional editor configuration.

This makes it easy to manage complex arrays in the UI while still enforcing validation rules defined in the items field.
Example of an array of strings property with sub-schema

{
    "title": "Start URLs",
    "type": "array",
    "description": "List of URLs for the scraper to visit",
    "editor": "schemaBased",
    "items": {
        "type": "string",
        "pattern": "^https?:\\/\\/(?:[a-zA-Z0-9-]+\\.)+[a-zA-Z]{2,}(?:\\/\\S*)?$"
    },
    "minItems": 1,
    "maxItems": 50,
    "uniqueItems": true
}

Rendered input: Apify Actor input schema with sub-schema array string

    Each item is rendered as a text field.
    The array must contain between 1 and 50 items.
    Duplicate values are not allowed.

Example of an array of objects property with sub-schema

{
    "title": "Request Headers",
    "type": "array",
    "description": "List of custom HTTP headers",
    "editor": "schemaBased",
    "items": {
        "type": "object",
        "properties": {
            "name": {
                "title": "Header Name",
                "description": "Name of the HTTP header",
                "type": "string",
                "minLength": 1,
                "editor": "textfield"
            },
            "value": {
                "title": "Header Value",
                "description": "Value of the HTTP header",
                "type": "string",
                "minLength": 1,
                "editor": "textfield"
            }
        },
        "required": ["name", "value"],
        "additionalProperties": false
    },
    "minItems": 1,
    "maxItems": 20
}

Rendered input: Apify Actor input schema with sub-schema array object

    Each array item is represented as a group of input fields (name and value).
    Validation ensures all required sub-properties are filled and no extra properties are allowed.
    New items can be added up to the maxItems limit, and each item is validated individually.

Limitations

As with objects, the sub-schema feature for arrays only works for level 1 sub-properties. While the objects in the array can have properties with their own schema definitions, those properties cannot themselves use the schemaBased editor.
Resource type

Resource type identifies what kind of Apify Platform object is referred to in the input field. For example, the Key-value store resource type can be referred to using a string ID. Currently, it supports storage resources only, allowing the reference of a Dataset, Key-Value Store or Request Queue.

For Actor developers, the resource input value is a string representing either the resource ID or (unique) name. The type of the property is either string or array. In case of array (for multiple resources) the return value is an array of IDs or names. In the user interface, a picker (resourcePicker editor) is provided for easy selection, where users can search and choose from their own resources or those they have access to.

Example of a Dataset input:

{
    "title": "Dataset",
    "type": "string",
    "description": "Select a dataset",
    "resourceType": "dataset"
}

Rendered input:

Apify Actor input schema dataset

The returned value is resource reference, in this example it's the dataset ID as can be seen in the JSON tab:

Apify Actor input schema dataset

Example of multiple datasets input:

{
    "title": "Datasets",
    "type": "array",
    "description": "Select multiple datasets",
    "resourceType": "dataset",
    "resourcePermissions": ["READ"]
}

Rendered input:

Apify Actor input schema datasets
Single value properties
Property	Value	Required	Description
type	string	Yes	Specifies the type of input - string for single value.
editor	One of

    resourcePicker
    textfield
    hidden

	No	Visual editor used for
the input field. Defaults to resourcePicker.
resourceType	One of

    dataset
    keyValueStore
    requestQueue

	Yes	Type of Apify Platform resource
resourcePermissions	Array of strings; allowed values:

    READ
    WRITE

	Yes	Permissions requested for the referenced resource. Use ["READ"] for read-only access, or ["READ", "WRITE"] to allow writes.
pattern	String	No	Regular expression that will be used to validate the input. If validation fails, the Actor will not run.
minLength	Integer	No	Minimum length of the string.
maxLength	Integer	No	Maximum length of the string.
Multiple values properties
Property	Value	Required	Description
type	array	Yes	Specifies the type of input - array for multiple values.
editor	One of

    resourcePicker
    hidden

	No	Visual editor used for
the input field. Defaults to resourcePicker.
resourceType	One of

    dataset
    keyValueStore
    requestQueue

	Yes	Type of Apify Platform resource
resourcePermissions	Array of strings; allowed values:

    READ
    WRITE

	Yes	Permissions requested for the referenced resources. Use ["READ"] for read-only access, or ["READ", "WRITE"] to allow writes. Applies to each selected resource.
minItems	Integer	No	Minimum number of items the array can contain.
maxItems	Integer	No	Maximum number of items the array can contain.
Resource permissions

If your Actor runs with limited permissions, it must declare what access it needs to resources supplied via input. The resourcePermissions field defines which operations your Actor can perform on user-selected storages. This field is evaluated at run start and expands the Actor's limited permissions scope to access resources sent via input.

    ["READ"] - The Actor can read from the referenced resources.
    ["READ", "WRITE"] - The Actor can read from and write to the referenced resources.

Runtime behavior

This setting defines runtime access only and doesn't change field visibility or whether the field is required in the UI. For array fields (type: array), the same permissions apply to each selected resource. Your Actor's run will fail with an insufficient-permissions error if it attempts an operation without the required permission, such as writing with read-only access. Users can see the required permissions in the input field's tooltip.
Deprecation of patternKey and patternValue
Deprecation notice

The following properties are deprecated and will only be supported until June 30, 2026:

    patternKey - Used to validate keys in objects and arrays
    patternValue - Used to validate values in objects and arrays

These properties are being deprecated to better align with the JSON schema specification. By moving to standard JSON schema, a more consistent experience is provided that matches industry standards while enabling more powerful validation capabilities through the ability to define sub-properties.
Alternatives for arrays

For arrays, you can replace patternKey and patternValue by using the items property with a subschema.

Example of replacing patternValue for an array of strings:
Old approach with patternValue

{
    "title": "Tags",
    "type": "array",
    "description": "Enter tags",
    "editor": "stringList",
    "patternValue": "^[a-zA-Z0-9-_]+$"
}

New approach with items subschema

{
    "title": "Tags",
    "type": "array",
    "description": "Enter tags",
    "editor": "stringList",
    "items": {
        "type": "string",
        "pattern": "^[a-zA-Z0-9-_]+$"
    }
}

Example of replacing both patternKey and patternValue for an array with key-value pairs:
Old approach with patternKey and patternValue

{
    "title": "Headers",
    "type": "array",
    "description": "HTTP headers",
    "editor": "keyValue",
    "patternKey": "^[a-zA-Z0-9-]+$",
    "patternValue": "^.+$"
}

New approach with items subschema

{
    "title": "Headers",
    "type": "array",
    "description": "HTTP headers",
    "editor": "keyValue",
    "items": {
        "type": "object",
        "properties": {
            "key": {
                "title": "Name",
                "type": "string",
                "description": "Header name",
                "pattern": "^[a-zA-Z0-9-]+$"
            },
            "value": {
                "title": "Value",
                "type": "string",
                "description": "Header value",
                "pattern": "^.+$"
            }
        },
        "required": ["key", "value"]
    }
}

Alternatives for objects

For objects, there is currently no direct replacement for patternKey and patternValue properties. These validation features will not be supported in future versions.

If you need to validate object properties, consider using a predefined schema with the properties field instead of allowing arbitrary properties with validation patterns.

Secret input

Copy for LLM

The secret input feature lets you mark specific input fields of an Actor as sensitive. When you save the Actor's input configuration, the values of these marked fields get encrypted. The encrypted input data can only be decrypted within the Actor. This provides an extra layer of security for sensitive information like API keys, passwords, or other confidential data.
How to set a secret input field

To make an input field secret, you need to add a "isSecret": true setting to the input field in the Actor's input schema, like this:

{
    // ...
    "properties": {
        // ...
        "password": {
            "title": "Password",
            "type": "string",
            "description": "A secret, encrypted input field",
            "editor": "textfield",
            "isSecret": true
        },
        // ...
    },
    // ...
}

The editor for this input field will then turn into a secret input, and when you edit the field value, it will be stored encrypted.
Secret input editor

When you run the Actor through the API, the system automatically encrypts any input fields marked as secret before saving them to the Actor run's default key-value store.
Type restriction

This feature supports string, object, and array input types. Available editor types include:

    hidden (for any supported input type)
    textfield and textarea (for string inputs)
    json (for object and array inputs)

Read secret input fields

When you read the Actor input through Actor.getInput(), the encrypted fields are automatically decrypted. Decryption of string fields is supported since JavaScript SDK 3.1.0; support for objects and arrays was added in JavaScript SDK 3.4.2 and Python SDK 2.7.0.

> await Actor.getInput();
{
    username: 'username',
    password: 'password'
}

If you read the INPUT key from the Actor run's default key-value store directly, you will still get the original, encrypted input value.

> await Actor.getValue('INPUT');
{
    username: 'username',
    password: 'ENCRYPTED_VALUE:Hw/uqRMRNHmxXYYDJCyaQX6xcwUnVYQnH4fWIlKZL...'
}

Encryption mechanism

The encryption mechanism used for encrypting the secret input fields is the same dual encryption as in PGP. The secret input field is encrypted using a random key, using the aes-256-gcm cipher, and then the key is encrypted using a 2048-bit RSA key.

The RSA key is unique for each combination of user and Actor, ensuring that no Actor can decrypt input intended for runs of another Actor by the same user, and no user can decrypt input runs of the same Actor by a different user. This isolation of decryption keys enhances the security of sensitive input data.

During Actor execution, the decryption keys are passed as environment variables, restricting the decryption of secret input fields to occur solely within the context of the Actor run. This approach prevents unauthorized access to sensitive input data outside the Actor's execution environment.
Example Actor

If you want to test the secret input live, check out the Example Secret Input Actor in Apify Console. If you want to dig in deeper, you can check out its source code on GitHub.

Custom error messages

Copy for LLM

When an input fails validation against an Actor's input schema, the resulting errors are processed and displayed to the user. By default, these messages are generic and may not clearly explain what the validation rule actually means.

Custom error messages allow Actor developers to define tailored feedback messages for input validation errors, making it easier for users to understand what is required and improving overall usability.
The problem with generic error messages

Some validation rules have a specific purpose that generic error messages don't explain well. For example, consider the following input field using the pattern validation keyword:

{
  "title": "Email address",
  "type": "string",
  "description": "Your email address",
  "editor": "textfield",
  "pattern": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
}

Input that doesn't satisfy the pattern will produce an error message like:

Field "email" should match pattern "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$".

However, a message such as the following would be much more understandable for the user:

Field "email" must be a valid email address.

Custom error messages for input fields

Each property in the input schema can include an errorMessage field that defines a custom error message to be displayed when validation of that field fails.

The errorMessage must be an object that maps validation keywords (e.g., type, pattern, minLength) to their respective custom messages.
Email input with custom error messages

{
  "title": "Email address",
  "type": "string",
  "description": "Your email address",
  "editor": "textfield",
  "pattern": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$",
  "errorMessage": {
    "type": "Email must be a string",
    "pattern": "Email must be a valid email address"
  }
}

If a validation error occurs for a keyword that is not listed in the errorMessage object, the system will fall back to the default error message.
User-friendly messages

Custom error messages are especially useful for complex validation rules like regular expressions, where the default error message would show the entire pattern, which is not user-friendly. Refer to the best practices for more guidance.
Supported validation keywords

You can define custom error messages for any validation keyword supported by the input schema, including:
Type	Supported validation keywords
string	type, pattern, minLength, maxLength, enum
number/integer	type, minimum, maximum
boolean	type
array	type, minItems, maxItems, uniqueItems, patternKey, patternValue
object	type, minProperties, maxProperties, patternKey, patternValue
Nested properties

It's possible to define custom error messages in sub-properties as well. For objects with nested properties, you can define error messages at any level of nesting:

{
  "title": "User",
  "type": "object",
  "description": "Provide user details",
  "editor": "schemaBased",
  "properties": {
    "email": {
      "type": "string",
      "pattern": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$",
      "errorMessage": {
        "pattern": "Please enter a valid email address"
      }
    }
  }
}

Best practices

Custom error messages can be useful in specific cases, but they aren't always necessary. In most situations, the default validation messages are clear enough and ensure consistency across the platform. Use custom messages only when they meaningfully improve clarity - for example, when the default message would expose an unreadable regular expression or fail to explain a non-obvious requirement.
Actor output schema

Copy for LLM

The Actor output schema builds upon the schemas for the dataset and key-value store. It specifies where an Actor stores its output and defines templates for accessing that output. Apify Console uses these output definitions to display run results, and the Actor run's GET endpoint includes them in the output property.
Why output schema matters

Output schema is essential for:

    AI agent integration: When agents use Actors through the MCP server or API, they need to know what results to expect. Without output schema, agents cannot effectively chain Actors or process results.
    User experience: Clear output definitions help users understand what data they will receive before running an Actor.
    API consumers: The output schema appears in the GET Run API response, enabling programmatic discovery of Actor outputs.

Define output schema

Even if your Actor produces no output, define an empty output schema. This tells users and AI agents that the Actor completed successfully with no output, rather than assuming the run failed.
Structure

Place the output configuration files in the .actor folder in the Actor's root directory.

You can organize the files using one of these structures:
Single configuration file
.actor/actor.json

{
    "actorSpecification": 1,
    "name": "files-scraper",
    "title": "Files scraper",
    "version": "1.0.0",
    "output": {
        "actorOutputSchemaVersion": 1,
        "title": "Output schema of the files scraper",
        "properties": { /* define your outputs here */ }
    }
}

Separate configuration files
.actor/actor.json

{
    "actorSpecification": 1,
    "name": "files-scraper",
    "title": "Files scraper",
    "version": "1.0.0",
    "output": "./output_schema.json"
}

.actor/output_schema.json

{
    "actorOutputSchemaVersion": 1,
    "title": "Output schema of the files scraper",
    "properties": { /* define your outputs here */ }
}

Definitions

The output schema defines the collections of keys and their properties. It allows you to organize and validate data stored by the Actor, making it easier to manage and retrieve specific records.
Output schema object definition
Property	Type	Required	Description
actorOutputSchemaVersion	integer	true	Specifies the version of output schema structure document.
Currently only version 1 is available.
title	string	true	Title of the schema
description	string	false	Description of the schema
properties	Object	true	An object where each key is an output ID and its value is an Output object definition (see below).
Output object definition
Property	Type	Required	Description
title	string	true	The output's title, shown in the run's output tab if there are multiple outputs and in API as key for the generated output URL.
description	string	false	A description of the output. Only used when reading the schema (useful for LLMs).
template	string	true	Defines a URL template that generates the output link using {{variable}} syntax. See How templates work for details.
Available template variables
Variable	Type	Description
links	object	Contains quick links to most commonly used URLs
links.publicRunUrl	string	Public run url in format https://console.apify.com/view/runs/:runId
links.consoleRunUrl	string	Console run url in format https://console.apify.com/actors/runs/:runId
links.apiRunUrl	string	API run url in format https://api.apify.com/v2/actor-runs/:runId
links.apiDefaultDatasetUrl	string	API url of default dataset in format https://api.apify.com/v2/datasets/:defaultDatasetId
links.apiDefaultKeyValueStoreUrl	string	API url of default key-value store in format https://api.apify.com/v2/key-value-stores/:defaultKeyValueStoreId
run	object	Contains information about the run same as it is returned from the GET Run API endpoint
run.containerUrl	string	URL of a webserver running inside the run in format https://<containerId>.runs.apify.net/
run.defaultDatasetId	string	ID of the default dataset
run.defaultKeyValueStoreId	string	ID of the default key-value store
storages	object	Contains references to named storages defined in the Actor's storage configuration
storages.datasets.<name>.apiUrl	string	API URL of a named dataset in format https://api.apify.com/v2/datasets/:datasetId
storages.keyValueStores.<name>.apiUrl	string	API URL of a named key-value store in format https://api.apify.com/v2/key-value-stores/:keyValueStoreId
How templates work

Templates allow you to dynamically generate URLs that point to your Actor's output. When an Actor run completes, the Apify platform processes each template by:

    Replacing {{variable}} placeholders with actual runtime values
    Creating the final output URL from the interpolated template

The generated URL then appears in the Output tab of Apify Console and in the output property of the API response.
Template syntax

Templates use double curly braces {{variable}} for variable interpolation.

    {{links.apiDefaultDatasetUrl}}/items becomes https://api.apify.com/v2/datasets/<dataset-id>/items
    {{run.containerUrl}} becomes https://<container-id>.runs.apify.net/

You can access nested properties using dot notation (e.g., {{run.defaultDatasetId}}, {{links.publicRunUrl}}).
Examples
Linking default dataset

The following example Actor calls Actor.pushData() to store results in the default dataset:
main.js

import { Actor } from 'apify';
// Initialize the JavaScript SDK
await Actor.init();

/**
 * Store data in default dataset
 */
await Actor.pushData({ title: 'Some product', url: 'https://example.com/product/1', price: 9.99 });
await Actor.pushData({ title: 'Another product', url: 'https://example.com/product/2', price: 4.99 });

// Exit successfully
await Actor.exit();

To specify that the Actor is using output schema, update the .actor/actor.json file:
.actor/actor.json

{
    "actorSpecification": 1,
    "name": "Actor Name",
    "title": "Actor Title",
    "version": "1.0.0",
    "output": "./output_schema.json"
}

Then to specify that output is stored in the default dataset, create .actor/output_schema.json:
.actor/output_schema.json

{
    "actorOutputSchemaVersion": 1,
    "title": "Output schema of the Actor",
    "properties": {
        "results": {
            "type": "string",
            "title": "Results",
            "template": "{{links.apiDefaultDatasetUrl}}/items"
        }
    }
}

To show that the output is stored in the default dataset, the schema defines a property called results.

The title is a human-readable name for the output, shown in Apify Console.

The template uses a variable {{links.apiDefaultDatasetUrl}}, which is replaced with the URL of the default dataset when the Actor run finishes.

Apify Console uses this configuration to display dataset data.

The Output tab will then display the contents of the dataset:

Output tab in Run

The GET Run API endpoint response will include an output property.

"output": {
    "results": "https://api.apify.com/v2/datasets/<dataset-id>/items"
}

Linking to key-value store

Similar to the example of linking to default dataset, the following example Actor calls Actor.setValue() to store files in the default key-value store:
main.js

import { Actor } from 'apify';
// Initialize the JavaScript SDK
await Actor.init();

/**
 * Store data in key-value store
 */
await Actor.setValue('document-1.txt', 'my text data', { contentType: 'text/plain' });
await Actor.setValue(`image-1.jpeg`, imageBuffer, { contentType: 'image/jpeg' });

// Exit successfully
await Actor.exit();

To specify that the Actor is using output schema, update the .actor/actor.json file:
.actor/actor.json

{
    "actorSpecification": 1,
    "name": "Actor Name",
    "title": "Actor Title",
    "version": "1.0.0",
    "output": "./output_schema.json"
}

Then to specify that output is stored in the key-value store, update .actor/output_schema.json:
.actor/output_schema.json

{
    "actorOutputSchemaVersion": 1,
    "title": "Output schema of the Actor",
    "properties": {
        "files": {
            "type": "string",
            "title": "Files",
            "template": "{{links.apiDefaultKeyValueStoreUrl}}/keys"
        }
    }
}

To show that the output is stored in the default key-value store, the schema defines a property called files.

The template uses a variable {{links.apiDefaultKeyValueStoreUrl}}, which is replaced with the URL of the default key-value store API endpoints when the Actor run finishes.

Apify Console uses this configuration to display key-value store data.

The Output tab will then display the contents of the key-value store:

Output tab in Run

The GET Run API endpoint response will include an output property.

"output": {
    "files": "https://api.apify.com/v2/key-value-stores/<key-value-store-id>/keys"
}

Linking dataset views and key-value store collections

This example shows a schema definition for a basic social media scraper. The scraper downloads post data into the dataset, and video and subtitle files into the key-value store.

After you define views and collections in dataset_schema.json and key_value_store.json, you can use them in the output schema.
Output schema complements dataset schema

The output schema defines where data is stored and how to access it. The dataset schema defines what fields each item contains, including descriptions and examples. Use both schemas together:

    Output schema: Declares that results are in the default dataset
    Dataset schema: Describes each field with title, description, and example

This combination gives AI agents complete information about your Actor's output structure.
.actor/output_schema.json

{
    "actorOutputSchemaVersion": 1,
    "title": "Output schema of Social media scraper",
    "properties": {
        "overview": {
            "type": "string",
            "title": "Results",
            "template": "{{links.apiDefaultDatasetUrl}}/items"
        },
        "subtitleFiles": {
            "type": "string",
            "title": "Subtitle files",
            "template": "{{links.apiDefaultKeyValueStoreUrl}}/keys?collection=subtitles"
        },
        "videoFiles": {
            "type": "string",
            "title": "Video files",
            "template": "{{links.apiDefaultKeyValueStoreUrl}}/keys?collection=videos"
        }
    }
}

The schema above defines one dataset output and two key-value store outputs. The dataset output links to the entire dataset. In Apify Console, this displays as a table with a selector that lets users switch between views defined in the dataset schema. The key-value store outputs link to collections defined in the key-value store schema.

If you add a view parameter to the dataset URL template, users still see the entire dataset in Apify Console, but the specified view is selected by default.

When a user runs the Actor in the Console, the UI will look like this:

Video files in Output tab
Use container URL to display chat client

In this example, an Actor runs a web server that provides a chat interface to an LLM. The conversation history is then stored in the dataset.
.actor/output_schema.json

{
    "actorOutputSchemaVersion": 1,

    "title": "Chat client output",
    "description": "Chat client provides interactive view to converse with LLM and chat history in dataset",
    "type": "object",

    "properties": {
        "clientUrl": {
            "type": "string",
            "title": "Chat client",
            "template": "{{run.containerUrl}}"
        },
        "chatHistory": {
            "type": "string",
            "title": "Conversation history",
            "template": "{{links.apiDefaultDatasetUrl}}/items"
        }
    }
}

In the schema above we have two outputs. The clientUrl output will return a link to the web server running inside the run. The chatHistory links to the default dataset and contains the history of the whole conversation, with each message as a separate item.

When the run in the Console, the user will then see this:

Chat in Output tab
Custom HTML as Actor run output

This example shows an output schema of an Actor that runs Cypress tests. When the run finishes, the Actor generates an HTML report and store it in the key-value store. You can link to this file and show it as an output:
.actor/output_schema.json

{
    "actorOutputSchemaVersion": 1,

    "title": "Cypress test report output",
    "description": "Test report from Cypress",
    "type": "object",

    "properties": {
        "reportUrl": {
            "type": "string",
            "title": "HTML Report",
            "template": "{{links.apiDefaultKeyValueStoreUrl}}/records/report.html"
        }
    }
}

The reportUrl in this case links directly to the key-value store record stored in the default key-value store.

When the run finishes, Apify Console displays the HTML report in an iframe:

HTML report in Output tab
Web crawler with multiple output types

This example shows a complete output schema for a web crawler Actor with multiple output types: crawled page data, errors, and files stored in key-value store collections.
.actor/output_schema.json

{
    "$schema": "https://apify-projects.github.io/actor-json-schemas/output.json?v=0.3",
    "actorOutputSchemaVersion": 1,
    "title": "Output schema of the Actor",
    "properties": {
        "crawlResults": {
            "type": "string",
            "title": "Crawl results",
            "template": "{{links.apiDefaultDatasetUrl}}/items"
        },
        "screenshots": {
            "type": "string",
            "title": "Screenshots",
            "template": "{{links.apiDefaultKeyValueStoreUrl}}/keys?collection=screenshots"
        },
        "downloadedFiles": {
            "type": "string",
            "title": "Downloaded files",
            "template": "{{links.apiDefaultKeyValueStoreUrl}}/keys?collection=downloaded-files"
        },
        "htmlSnapshots": {
            "type": "string",
            "title": "HTML snapshots",
            "template": "{{links.apiDefaultKeyValueStoreUrl}}/keys?collection=html-snapshots"
        },
        "crawlErrors": {
            "type": "string",
            "title": "Errors",
            "template": "{{storages.datasets.errors.apiUrl}}/items"
        }
    }
}

Each output includes a description explaining what the data contains. This metadata helps AI agents understand the Actor's capabilities and select the appropriate output for their needs.
Actor with no output

If your Actor produces no output (for example, an integration Actor that performs an action), users might see the empty Output tab and think the Actor failed. To avoid this, specify that the Actor produces no output.

You can specify that the Actor produces no output and define an output schema with no properties:
.actor/output_schema.json

{
    "actorOutputSchemaVersion": 1,

    "title": "Send mail output",
    "description": "Send mail Actor does not generate any output.",
    "type": "object",
    "properties": {}
}

When the output schema contains no properties, Apify Console displays the Log tab instead of the Output tab.

Dataset schema specification

Copy for LLM

The dataset schema defines the structure and representation of data produced by an Actor, both in the API and the visual user interface.
Example

Let's consider an example Actor that calls Actor.pushData() to store data into dataset:
main.js

import { Actor } from 'apify';
// Initialize the JavaScript SDK
await Actor.init();

/**
 * Actor code
 */
await Actor.pushData({
    numericField: 10,
    pictureUrl: 'https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_92x30dp.png',
    linkUrl: 'https://google.com',
    textField: 'Google',
    booleanField: true,
    dateField: new Date(),
    arrayField: ['#hello', '#world'],
    objectField: {},
});

// Exit successfully
await Actor.exit();

To set up the Actor's output tab UI using a single configuration file, use the following template for the .actor/actor.json configuration:
.actor/actor.json

{
    "actorSpecification": 1,
    "name": "Actor Name",
    "title": "Actor Title",
    "version": "1.0.0",
    "storages": {
        "dataset": {
            "actorSpecification": 1,
            "views": {
                "overview": {
                    "title": "Overview",
                    "transformation": {
                        "fields": [
                            "pictureUrl",
                            "linkUrl",
                            "textField",
                            "booleanField",
                            "arrayField",
                            "objectField",
                            "dateField",
                            "numericField"
                        ]
                    },
                    "display": {
                        "component": "table",
                        "properties": {
                            "pictureUrl": {
                                "label": "Image",
                                "format": "image"
                            },
                            "linkUrl": {
                                "label": "Link",
                                "format": "link"
                            },
                            "textField": {
                                "label": "Text",
                                "format": "text"
                            },
                            "booleanField": {
                                "label": "Boolean",
                                "format": "boolean"
                            },
                            "arrayField": {
                                "label": "Array",
                                "format": "array"
                            },
                            "objectField": {
                                "label": "Object",
                                "format": "object"
                            },
                            "dateField": {
                                "label": "Date",
                                "format": "date"
                            },
                            "numericField": {
                                "label": "Number",
                                "format": "number"
                            }
                        }
                    }
                }
            }
        }
    }
}

The template above defines the configuration for the default dataset output view. Under the views property, there is one view titled Overview. The view configuration consists of two main steps:

    transformation - set up how to fetch the data.
    display - set up how to visually present the fetched data.

The default behavior of the Output tab UI table is to display all fields from transformation.fields in the specified order. You can customize the display properties for specific formats or column labels if needed.

Output tab UI
Structure

Output configuration files need to be located in the .actor folder within the Actor's root directory.

You have two choices of how to organize files within the .actor folder.
Single configuration file
.actor/actor.json

{
    "actorSpecification": 1,
    "name": "this-is-book-library-scraper",
    "title": "Book Library scraper",
    "version": "1.0.0",
    "storages": {
        "dataset": {
            "actorSpecification": 1,
            "fields": {},
            "views": {
                "overview": {
                    "title": "Overview",
                    "transformation": {},
                    "display": {}
                }
            }
        }
    }
}

Separate configuration files
.actor/actor.json

{
    "actorSpecification": 1,
    "name": "this-is-book-library-scraper",
    "title": "Book Library scraper",
    "version": "1.0.0",
    "storages": {
        "dataset": "./dataset_schema.json"
    }
}

.actor/dataset_schema.json

{
    "actorSpecification": 1,
    "fields": {},
    "views": {
        "overview": {
            "title": "Overview",
            "transformation": {},
            "display": {
                "component": "table"
            }
        }
    }
}

Both of these methods are valid so choose one that suits your needs best.
Handle nested structures

The most frequently used data formats present the data in a tabular format (Output tab table, Excel, CSV). If your Actor produces nested JSON structures, you need to transform the nested data into a flat tabular format. You can flatten the data in the following ways:

    Use transformation.flatten to flatten the nested structure of specified fields. This transforms the nested object into a flat structure. e.g. with flatten:["foo"], the object {"foo": {"bar": "hello"}} is turned into {"foo.bar": "hello"}. Once the structure is flattened, it's necessary to use the flattened property name in both transformation.fields and display.properties, otherwise, fields might not be fetched or configured properly in the UI visualization.

    Use transformation.unwind to deconstruct the nested children into parent objects.

    Change the output structure in an Actor from nested to flat before the results are saved in the dataset.

Dataset schema structure definitions

The dataset schema structure defines the various components and properties that govern the organization and representation of the output data produced by an Actor. It specifies the structure of the data, the transformations to be applied, and the visual display configurations for the Output tab UI.
DatasetSchema object definition
Property	Type	Required	Description
actorSpecification	integer	true	Specifies the version of dataset schema
structure document.
Currently only version 1 is available.
fields	JSONSchema compatible object	false	Schema of one dataset object.
Use JsonSchema Draft 2020-12 or
other compatible formats. Refer to Field schema section for details.
views	DatasetView object	true	An object with a description of an API
and UI views.
DatasetView object definition
Property	Type	Required	Description
title	string	true	The title is visible in UI in the Output tab
and in the API.
description	string	false	The description is only available in the API response.
transformation	ViewTransformation object	true	The definition of data transformation
applied when dataset data is loaded from
Dataset API.
display	ViewDisplay object	true	The definition of Output tab UI visualization.
ViewTransformation object definition
Property	Type	Required	Description
fields	string[]	true	Selects fields to be presented in the output.
The order of fields matches the order of columns
in visualization UI. If a field value
is missing, it will be presented as undefined in the UI.
unwind	string[]	false	Deconstructs nested children into parent object,
For example, with unwind:["foo"], the object {"foo": {"bar": "hello"}}
is transformed into {"bar": "hello"}.
flatten	string[]	false	Transforms nested object into flat structure.
For example, with flatten:["foo"] the object {"foo":{"bar": "hello"}}
is transformed into {"foo.bar": "hello"}.
omit	string[]	false	Removes the specified fields from the output.
Nested fields names can be used as well.
limit	integer	false	The maximum number of results returned.
Default is all results.
desc	boolean	false	By default, results are sorted in ascending based on the write event into the dataset.
If desc:true, the newest writes to the dataset will be returned first.
ViewDisplay object definition
Property	Type	Required	Description
component	string	true	Only the table component is available.
properties	Object	false	An object with keys matching the transformation.fields
and ViewDisplayProperty as values. If properties are not set, the table will be rendered automatically with fields formatted as strings, arrays or objects.
ViewDisplayProperty object definition
Property	Type	Required	Description
label	string	false	In the Table view, the label will be visible as the table column's header.
format	One of

    text
    number
    date
    link
    boolean
    image
    array
    object

	false	Describes how output data values are formatted to be rendered in the Output tab UI.
Field schema

The fields property in the dataset schema defines the structure of individual dataset items using JSON Schema. This schema enables validation and provides metadata that helps both humans and AI agents understand your Actor's output.
Why field descriptions matter

When AI agents interact with Actors through the MCP server or API, they rely on the field schema to understand what data the Actor produces. Including title, description, and example properties for each field enables agents to:

    Understand the meaning of each output field
    Chain Actors together by matching inputs to outputs
    Generate appropriate queries and handle responses correctly

Without this metadata, agents must infer field meanings from names alone, which leads to errors and a degraded experience.
Define field metadata

Each field in your schema can include standard JSON Schema properties:
Property	Type	Description
type	string	The data type (string, number, boolean, array, object, null).
title	string	A human-readable name for the field.
description	string	Explains what the field contains and how to interpret it.
example	any	A sample value that demonstrates the expected format.
enum	array	A list of allowed values for the field.
Example with field descriptions

The following example shows a dataset schema for a product scraper with full field metadata:
.actor/dataset_schema.json

{
    "actorSpecification": 1,
    "fields": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "productName": {
                "type": "string",
                "title": "Product name",
                "description": "The full name of the product as displayed on the product page.",
                "example": "Wireless Bluetooth Headphones"
            },
            "price": {
                "type": "number",
                "title": "Price",
                "description": "The current price in USD. Does not include shipping or taxes.",
                "example": 49.99
            },
            "currency": {
                "type": "string",
                "title": "Currency code",
                "description": "Three-letter ISO 4217 currency code.",
                "example": "USD",
                "enum": ["USD", "EUR", "GBP"]
            },
            "inStock": {
                "type": "boolean",
                "title": "In stock",
                "description": "Whether the product is currently available for purchase.",
                "example": true
            },
            "categories": {
                "type": "array",
                "title": "Categories",
                "description": "List of category names the product belongs to, from broadest to most specific.",
                "items": {
                    "type": "string"
                },
                "example": ["Electronics", "Audio", "Headphones"]
            },
            "url": {
                "type": "string",
                "title": "Product URL",
                "description": "Direct link to the product page.",
                "example": "https://example.com/products/wireless-headphones"
            }
        },
        "required": ["productName", "price", "url"]
    },
    "views": {
        "overview": {
            "title": "Overview",
            "transformation": {
                "fields": ["productName", "price", "inStock", "url"]
            },
            "display": {
                "component": "table",
                "properties": {
                    "url": {
                        "label": "Link",
                        "format": "link"
                    },
                    "inStock": {
                        "format": "boolean"
                    }
                }
            }
        }
    }
}

Dataset validation

Copy for LLM

To define a schema for a default dataset of an Actor run, you need to set fields property in the dataset schema.
info

The schema defines a single item in the dataset. Be careful not to define the schema as an array, it always needs to be a schema of an object.

Schema configuration is not available for named datasets or dataset views.

You can either do that directly through actor.json:
.actor.json

{
    "actorSpecification": 1,
    "storages": {
        "dataset": {
            "actorSpecification": 1,
            "fields": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string"
                    }
                },
                "required": ["name"]
            },
            "views": {}
        }
    }
}

Or in a separate file linked from the .actor.json:
.actor.json

{
    "actorSpecification": 1,
    "storages": {
        "dataset": "./dataset_schema.json"
    }
}

dataset_schema.json

{
    "actorSpecification": 1,
    "fields": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "name": {
                "type": "string"
            }
        },
        "required": ["name"]
    },
    "views": {}
}

important

Dataset schema needs to be a valid JSON schema draft-07, so the $schema line is important and must be exactly this value or it must be omitted:

"$schema": "http://json-schema.org/draft-07/schema#"
Dataset validation

When you define a schema of your default dataset, the schema is then always used when you insert data into the dataset to perform validation (we use AJV).

If the validation succeeds, nothing changes from the current behavior, data is stored and an empty response with status code 201 is returned.

If the data you attempt to store in the dataset is invalid (meaning any of the items received by the API fails validation), the entire request will be discarded, The API will return a response with status code 400 and the following JSON response:

{
    "error": {
        "type": "schema-validation-error",
        "message": "Schema validation failed",
        "data": {
            "invalidItems": [{
                "itemPosition": "<array index in the received array of items>",
                "validationErrors": "<Complete list of AJV validation error objects>"
            }]
        }
    }
}

For the complete AJV validation error object type definition, refer to the AJV type definitions on GitHub.

If you use the Apify JS client or Apify SDK and call pushData function you can access the validation errors in a try catch block like this:

    Javascript
    Python

try {
    const response = await Actor.pushData(items);
} catch (error) {
    if (!error.data?.invalidItems) throw error;
    error.data.invalidItems.forEach((item) => {
        const { itemPosition, validationErrors } = item;
    });
}

Examples of common types of validation

Optional field (price is optional in this case):

{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "name": {
            "type": "string"
        },
        "price": {
            "type": "number"
        }
    },
    "required": ["name"]
}

Field with multiple types:

{
    "price": {
        "type": ["string", "number"]
    }
}

Field with type any:

{
    "price": {
        "type": ["string", "number", "object", "array", "boolean"]
    }
}

Enabling fields to be null :

{
    "name": {
        "type": ["string", "null"]
    }
}

In case of enums null needs to be within the set of allowed values:

{
    "type": {
        "enum": ["list", "detail", null]
    }
}

Define type of objects in array:

{
    "comments": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "author_name": {
                    "type": "string"
                }
            }
        }
    }
}

Define specific fields, but allow anything else to be added to the item:

{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "name": {
            "type": "string"
        }
    },
    "additionalProperties": true
}

See json schema reference for additional options.

You can also use conversion tools to convert an existing JSON document into it's JSON schema.
Dataset field statistics

When you configure the dataset fields schema, we generate a field list and measure the following statistics:

    Null count: how many items in the dataset have the field set to null
    Empty count: how many items in the dataset are undefined , meaning that for example empty string is not considered empty
    Minimum and maximum
        For numbers, this is calculated directly
        For strings, this field tracks string length
        For arrays, this field tracks the number of items in the array
        For objects, this tracks the number of keys
        For booleans, this tracks whether the boolean was set to true. Minimum is always 0, but maximum can be either 1 or 0 based on whether at least one item in the dataset has the boolean field set to true.

You can use them in monitoring.
Multiple datasets

Copy for LLM

Actors that scrape different data types can store each type in its own dataset with separate validation rules. For example, an e-commerce scraper might store products in one dataset and categories in another.

Each dataset:

    Is created when the run starts
    Follows the run's data retention policy
    Can have its own validation schema

Define multiple datasets

Define datasets in your Actor schema using the datasets object:
.actor/actor.json

{
    "actorSpecification": 1,
    "name": "my-e-commerce-scraper",
    "title": "E-Commerce Scraper",
    "version": "1.0.0",
    "storages": {
        "datasets": {
            "default": "./products_dataset_schema.json",
            "categories": "./categories_dataset_schema.json"
        }
    }
}

Provide schemas for individual datasets as file references or inline. Schemas follow the same structure as single-dataset schemas.

The keys of the datasets object are aliases that refer to specific datasets. The previous example defines two datasets aliased as default and categories.
Alias versus named dataset

Aliases and names are different. Named datasets have specific behavior on the Apify platform (the automatic data retention policy doesn't apply to them). Aliased datasets follow the data retention of their run. Aliases only have meaning within a specific run.

Requirements:

    The datasets object must contain the default alias
    The datasets and dataset objects are mutually exclusive (use one or the other)

See the full Actor schema reference.
Access datasets in Actor code

Access aliased datasets: using the Apify SDK, or reading the ACTOR_STORAGES_JSON environment variable directly.
Apify SDK

    JavaScript
    Python

In the JavaScript/TypeScript SDK >=3.7.0, use openDataset with alias option:

const categoriesDataset = await Actor.openDataset({alias: 'categories'});

Running outside the Apify platform

When the JavaScript SDK runs outside the Apify platform, aliases fall back to names (using an alias is the same as using a named dataset). The dataset is purged on the first access when accessed using the alias option.
Environment variable

ACTOR_STORAGES_JSON contains JSON-encoded unique identifiers of all storages associated with the current Actor run. Use this approach when working without the SDK:

echo $ACTOR_STORAGES_JSON | jq '.datasets.categories'
# This will output id of the categories dataset, e.g. `"3ZojQDdFTsyE7Moy4"`

Configure the output schema
Storage tab

The Storage tab in the Actor run view displays all datasets defined by the Actor and used by the run (up to 10).

The Storage tab shows data but doesn't surface it clearly to end users. To present datasets more clearly, define an output schema.
Output schema

Actors with output schemas can reference datasets through variables using aliases:

{
    "actorOutputSchemaVersion": 1,
    "title": "Output schema",
    "properties": {
        "products": {
            "type": "string",
            "title": "Products",
            "template": "{{storages.datasets.default.apiUrl}}/items"
        },
        "categories": {
            "type": "string",
            "title": "Categories",
            "template": "{{storages.datasets.categories.apiUrl}}/items"
        }
    }
}

Read more about how templates work.
Billing for non-default datasets

When an Actor uses multiple datasets, only items pushed to the default dataset trigger the built-in apify-default-dataset-item event. Items in other datasets are not charged automatically.

To charge for items in other datasets, implement custom billing in your Actor code. Refer to the billing documentation for implementation details.

Builds and runs

Copy for LLM

Actor builds and runs are fundamental concepts within the Apify platform. Understanding them is crucial for effective use of the platform.
Build an Actor

When you start the build process for your Actor, you create a build. A build is a Docker image containing your source code and the required dependencies needed to run the Actor:

build process

Actor Definition files

Dockerfile

.actor/actor.json

src/main.js

Build
Run an Actor

To create a run, you take your build and start it with some input:

start Actor

Run Definition

Build

Input

Run
Lifecycle

Actor builds and runs share a common lifecycle. Each build and run begins with the initial status READY and progress through one or more transitional statuses to reach a terminal status.

Terminal states

Transitional states

RUNNING

TIMING-OUT

ABORTING

SUCCEEDED

FAILED

TIMED-OUT

ABORTED

READY
Status	Type	Description
READY	initial	Started but not allocated to any worker yet
RUNNING	transitional	Executing on a worker machine
SUCCEEDED	terminal	Finished successfully
FAILED	terminal	Run failed
TIMING-OUT	transitional	Timing out now
TIMED-OUT	terminal	Timed out
ABORTING	transitional	Being aborted by user
ABORTED	terminal	Aborted by user
Edit this page
Builds

Copy for LLM
Understand Actor builds

Before an Actor can be run, it needs to be built. The build process creates a snapshot of a specific version of the Actor's settings, including its source code and environment variables. This snapshot is then used to create a Docker image containing everything the Actor needs for its run, such as npm packages, web browsers, etc.
Build numbers

Each build is assigned a unique build number in the format MAJOR.MINOR.BUILD (e.g. 1.2.345):

    MAJOR.MINOR corresponds to the Actor version number
    BUILD is an automatically incremented number starting at 1.

Build resources

By default, builds have the following resource allocations:

    Timeout: 1800 seconds
    Memory: 4096 MB

Check out the Resource limits section for more details.
Versioning

To support active development, Actors can have multiple versions of source code and associated settings, such as the base image and environment. Each version is denoted by a version number of the form MAJOR.MINOR, following Semantic Versioning principles.

For example, an Actor might have:

    Production version 1.1
    Beta version 1.2 that contains new features but is still backward compatible
    Development version 2.0 that contains breaking changes.

Tags

Tags simplify the process of specifying which build to use when running an Actor. Instead of using a version number, you can use a tag such as latest or beta. Tags are unique, meaning only one build can be associated with a specific tag.

To set a tag for builds of a specific Actor version:

    Set the Build tag property.
    When a new build of that version is successfully finished, it's automatically assigned the tag.

By default, the builds are set to the latest tag.
Cache

To speed up builds triggered via API, you can use the useCache=1 parameter. This instructs the build process to use cached Docker images and layers instead of pulling the latest copies and building each layer from scratch. Note that the cached images and layers might not always be available on the server building the image, the useCache parameter only functions on a best-effort basis.
Clean builds

By default, Apify Console uses cached data when starting a build.

To run a clean build without using the cache:

    Go to your Actor page.
    Select Source > Code.
    Expand Build options and choose Clean build.

Runs

Copy for LLM

When you start an Actor, you create a run. A run is a single execution of your Actor with a specific input in a Docker container.
Starting an Actor

You can start an Actor in several ways:

    Manually from the Apify Console UI
    Via the Apify API
    Using the Scheduler provided by the Apify platform
    By one of the available integrations

Input and environment variables

The run receives input via the INPUT record of its default key-value store. Environment variables are also passed to the run. For more information about environment variables check the Environment variables section.
Run duration and timeout

Actor runs can be short or long-running. To prevent infinite runs, you can set a timeout. The timeout is specified in seconds, and the default timeout varies based on the template from which you create your Actor. If the run doesn't finish within the timeout, it's automatically stopped, and its status is set to TIMED-OUT.State persistence

Copy for LLM

Learn how to maintain an Actor's state to prevent data loss during unexpected restarts. Includes code examples for handling server migrations.

Long-running Actor jobs may need to migrate between servers. Without state persistence, your job's progress is lost during migration, causing it to restart from the beginning on the new server. This can be costly and time-consuming.

To prevent data loss, long-running Actors should persist their state so they can resume from where they left off after a migration.

For short-running Actors, the risk of restarts and the cost of repeated runs are low, so you can typically ignore state persistence.
Understand migrations

A migration occurs when a process running on one server must stop and move to another. During this process:

    All in-progress processes on the current server are stopped
    Unless you've saved your state, the Actor run will restart on the new server with an empty internal state
    You only have a few seconds to save your work when a migration event occurs

Causes of migration

Migrations can happen for several reasons:

    Server workload optimization
    Server crashes (rare)
    New feature releases and bug fixes

Frequency of migrations

Migrations don't follow a specific schedule. They can occur at any time due to the events mentioned above.
Why state is lost during migration

By default, an Actor keeps its state in the server's memory. During a server switch, the run loses access to the previous server's memory. Even if data were saved on the server's disk, access to that would also be lost. Note that the Actor run's default dataset, key-value store and request queue are preserved across migrations, by state we mean the contents of runtime variables in the Actor's code.
Implement state persistence

Use the JS SDK's Actor.useState() or Python SDK's Actor.use_state() methods to persist state across migrations. This method automatically saves your state to the key-value store and restores it when the Actor restarts.

    JavaScript
    Python

import { Actor } from 'apify';

await Actor.init();

const state = await Actor.useState({ itemCount: 0, lastOffset: 0 });

// The state object is automatically persisted during migrations.
// Update it as your Actor processes data.
state.itemCount += 1;
state.lastOffset = 100;

await Actor.exit();

For improved Actor performance, consider caching repeated page data.
Speed up migrations and ensure consistency

Once your Actor receives the migrating event, the Apify platform will shut it down and restart it on a new server within one minute. To speed this process up and ensure state consistency, you can manually reboot the Actor in the migrating event handler using the Actor.reboot() method available in the Apify SDK for JavaScript or Apify SDK for Python.

    JavaScript
    Python

import { Actor } from 'apify';

await Actor.init();
// ...
Actor.on('migrating', async () => {
    // ...
    // save state
    // ...
    await Actor.reboot();
});
// ...
await Actor.exit();