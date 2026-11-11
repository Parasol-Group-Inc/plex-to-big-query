Please rate the new Quick notes tab by taking a short survey.

Emilio / Jennilyn

Nov 11, 2026
Emilio Dominguez Jennilyn Tockstein

Data extraction challenges and cloud billing migration were reviewed with repository access adjustments

Plex Data Hub and Label Design Updates
Emilio added customer nodes and new tabs to the Plex data hub.
ODBC data experiences a 4-hour lag or freezes entirely from the previous day.
Live screens provide an immediate and reliable source of truth for label design.
ODBC performs full data extraction during early morning hours around 4:00 AM.
Container statuses marked expired past use-by dates are forced back into inventory valuation.

Dashboard and Data Views
Justin created proposed dashboards and resolved token issues for Kaya and ODF.
Jennilyn built custom views in Vox scorecards live to track Rev and Whip parts.
Held inventory views provide the sales team with order tracking within an 8-hour delay.

Cloud Infrastructure and Billing Management
Vox scripts can mostly be trashed while Parasol marketing scripts remain active.
Ha's scripts running every 10 minutes drive up operational costs significantly.
Separate billing will be established for major companies to monitor monthly usage accurately.
PCS software projects require separate billing because Ha's scripts consume excessive resources.

Next steps
[Emilio Dominguez] Back up Jennilyn's custom views: and document them on the Plex data hub to serve as a reference for what they contain.
[Emilio Dominguez] Take a look at personal account numbers: to clean them up and verify the account details.
[Emilio Dominguez] Add Jennilyn to the Plex ETL GitHub repository: to ensure proper access to the project code.
[Emilio Dominguez] Message Kelly regarding label design info: to provide the necessary updates from yesterday.
[Emilio Dominguez] Inform Kelly: about the new process regarding data missing on columns and live screen portal information.
[Emilio Dominguez] Send an email: containing the web services needed out of their name to allow setting up new accounts.
[Jennilyn Tockstein] Transfer Google Cloud billing and project ownership: out of personal accounts and under parasol bisops by next week.
[Jennilyn Tockstein] Create new accounts and open cases: for the web services and items set up under Emilio's name after receiving the email.




Want to see more? View the full notes
Tip: You can always access your full notes from the left sidebar.



You should review Gemini's notes to make sure they're accurate. Get tips and learn how Gemini takes notes


Nov 11, 2026
Emilio / Jennilyn
Invited Emilio Dominguez Jennilyn Tockstein
Attachments Emilio / Jennilyn
Meeting records Transcript 


Summary
Data extraction challenges and cloud billing migration were reviewed with repository access adjustments

Data Extraction And Views
Open Database Connectivity extraction delays required shifting immediate label design data to application programming interfaces or live screens. Container status adjustments in Plex views were documented on the hub.

Google Cloud Billing Migration
Google Cloud billing ownership will transfer to parasol bisops to separate company spending and mitigate security risks. Service accounts will replace developer credentials for extractions.


Decisions
Needs Further Discussion
Container status inventory handling Jennilyn forced containers past their use-by date back into inventory valuation and is unsure whether to also force them back into on-hand inventory.

Aligned
Establish ODBC morning extraction standard The group established that ODBC will serve as the source of truth for the morning full data extraction around 4:00 AM to 5:00 AM.
Use live screens for label design The team aligned to use API or live screens as the immediate source of truth for label design throughout the day.
Transfer Google Cloud ownership and billing The participants agreed to transfer all Google Cloud billing ownership and project ownership out of Jennilyn's name and under Parasol bisops, separating smaller companies and major ones into their own billings.
Establish company-specific Google account seats The group agreed to use separate paid seats for each company and Parasol while keeping the overall Google account as Parasol bisops with shared project ownership.


Next steps
[Emilio Dominguez] Back up Jennilyn's custom views: and document them on the Plex data hub to serve as a reference for what they contain.
[Emilio Dominguez] Take a look at personal account numbers: to clean them up and verify the account details.
[Emilio Dominguez] Add Jennilyn to the Plex ETL GitHub repository: to ensure proper access to the project code.
[Emilio Dominguez] Message Kelly regarding label design info: to provide the necessary updates from yesterday.
[Emilio Dominguez] Inform Kelly: about the new process regarding data missing on columns and live screen portal information.
[Emilio Dominguez] Send an email: containing the web services needed out of their name to allow setting up new accounts.
[Jennilyn Tockstein] Transfer Google Cloud billing and project ownership: out of personal accounts and under parasol bisops by next week.
[Jennilyn Tockstein] Create new accounts and open cases: for the web services and items set up under Emilio's name after receiving the email.


Details
Label Design and Open Database Connectivity Data Extraction Challenges: Emilio Dominguez reported on the new customer nodes tabs and explained three potential angles for label design work: using live screens, the application programming interface, and Open Database Connectivity. The problem is that Open Database Connectivity either lags for four hours or freezes entirely from the previous day, though it performs full data extractions reliably in the early morning between 4:00 AM and 5:00 AM. Emilio Dominguez noted that while Open Database Connectivity serves as a source of truth for morning extractions, the application programming interface or live screens should be used for immediate label design data. Jennilyn Tockstein and Emilio Dominguez discussed how new orders, sales representatives, and customers are managed through these logic checks (00:00:06) (00:03:04).

Customer Notes and Data Audits: Emilio Dominguez updated Jennilyn Tockstein on customer notes, explaining that existing notes were appended rather than erased, and inactive customers were intentionally excluded unless potentially useful (00:04:29). Emilio Dominguez ran frequent audits for data logic and numbers, which are now logged in a dedicated tab. Additionally, Emilio Dominguez mentioned that Justin helped fix token issues with Kaya and Open Data Foundation, resulting in proposed dashboards pushed into BigQuery (00:06:07).


Resolving Missing Order Information and Live Screen Updates: Jennilyn Tockstein brought up an issue where Callie missed information because live screens failed to provide complete order statuses while Open Database Connectivity was frozen (00:07:43). Emilio Dominguez explained that this was a stale data issue caused by incomplete live screen statuses combined with the frozen Open Database Connectivity, which has now been fixed. Emilio Dominguez implemented multiple angles to check for order status changes and push updates when Open Database Connectivity fails to trigger them (00:09:09). Jennilyn Tockstein requested that Emilio Dominguez inform Callie about this new process (00:10:50).


Plex Product Views and Container Status Adjustments: Jennilyn Tockstein created new views based on Plex products—such as revenue and work in process, held inventory, and sales team order lookups—with an approximate eight-hour delay (00:10:50). A specific problem arose where Plex marks container statuses as expired once past the use-by date even if the expiration date has not passed, removing them from inventory valuation and on-hand counts. Jennilyn Tockstein forced containers back into inventory valuation and considered doing the same for on-hand counts. Emilio Dominguez agreed to back up and document these custom views on the hub along with project backups and docking containers (00:12:08).


Google Cloud Billing and Project Ownership Migration: Jennilyn Tockstein announced plans to transfer all Google Cloud assets, billing ownership, and project ownership out of their personal name and under parasol bisops by the following week (00:13:16) (00:17:13). Jennilyn Tockstein wants to separate billing for larger companies—including on-demand, ship central, QSM, and a separate project for PCS software—to easily track monthly spending. Jennilyn Tockstein noted that scripts on the PCS project managed by Ha run every ten minutes, driving up costs, while Emilio Dominguez explained that prop logic checks contribute to these expenses (00:14:51). Jennilyn Tockstein also plans to clean up inactive views, such as old NetSuite data, during this transition to mitigate security risks associated with personal account ownership (00:17:13).


Security, Service Accounts, and Repository Access: Jennilyn Tockstein and Emilio Dominguez discussed implementing service accounts for extractions and prop logic to avoid relying on developer credentials, noting that opening a Plex case is required for new service account emails. They debated consolidating Google account ownership versus splitting them across multiple areas using paid seats or Zoho Bolt to maintain redundancy and restricted project access (00:17:13) (00:19:21). To improve tracking and code management, Emilio Dominguez agreed to add Jennilyn Tockstein to the GitHub repository for the Plex Extract, Transform, and Load project (00:23:04).


Manual Data App Updates and Next Steps: Jennilyn Tockstein and Emilio Dominguez reviewed recent changes to the manual data application from App Script, which now includes a six-month period. Jennilyn Tockstein edited the manual table and advised that small changes, such as ten items, are easier to handle via the app, whereas large updates, such as 200 items, require a table upload (00:24:36). Emilio Dominguez will continue monitoring Open Database Connectivity performance to determine if live screens can fully replace it for label design (00:26:00). To wrap up, Jennilyn Tockstein asked Emilio Dominguez to send an email detailing all web services and accounts set up under Emilio Dominguez's name so Jennilyn Tockstein can create new accounts, open a case, and coordinate the migration (00:27:36).


You should review Gemini's notes to make sure they're accurate. Get tips and learn how Gemini takes notes
How is the quality of these specific notes? Take a short survey to let us know your feedback, including how helpful the notes were for your needs.


Nov 11, 2026
Emilio / Jennilyn - Transcript
00:00:06

Emilio Dominguez: All right, I think that's that's it. Let me get you. Sorry. Um on the hub on the Plex data hub we have the the work done for the customer nodes. So you'll see a bunch of bunch of new tabs um at the end. So you asked me also if we were using the API for the label design work. So initially I I wasn't I was working with just the live the live screens just getting crown to jump into the website and do the things but we also have another angle that could be possible to just have us as a reference of the API being a source of also of truth for that. So there are like these three angles that the label design can take, label design can take. Uh since the ODBC can either lag for those four hours or either or froze entirely from the day before and since those um orders are now being mapped entirely by the lives the live capture on the on the portal. So that's an angle.


00:01:44

Emilio Dominguez: Then there's another but not everything is captured. the sales rep and a new part or even a a new customer can be just be blanked when it's instructed because it is just the we are not getting everything right OBBC is is getting us everything but it is a reference that okay so those new orders are in so we can extract them if they are they meet the criteria then pass them into Monday and then update the Monday item for the sales rep and things that weren't updated if things were new totally new. Um I really don't know how frequent is to have a new part or a new customer right uh but it is also being taken care on on that logic. So yeah um since the last talk so it seems like the LDBC is quite good at the full instruction in the morning in the early morning like 4:00 a.m. So that's good. But then it just continues to not deliver the data. And I think that's by design because you told me initially, okay, we were going to have four hours of of gap.


00:03:04

Emilio Dominguez: So that's that wasn't the case before,
Jennilyn Tockstein: Mhm.
Emilio Dominguez: but it is now being seen right now. So maybe they are kind of pushing that harder because of computing power or I don't know what was the problem with them. Uh but yeah maybe they are just queuing having this queue for for clients to not deliver data because maybe there is just millions of ruggs to be delivered by OBBC. So the conclusion or the point is just to get OBBC to have this sort of truth but for the day once at the morning during the mornings on the full extraction of 4:00 a.m. 5 5:00 a.m. and then just keep probing keep uh extracting things whether from the API or the the live screens are immediate. they are a very good source of truth for label design. Uh so yeah that was the work done and it's been also polished uh each day so you could have a look if when you have the time to those those tabs the label design tab the reability um the the important one that you asked me before was that of the customer notes.


00:04:29

Emilio Dominguez: So that's also done but there were some flags. Let me just So there were some existing notes there. So there were there weren't like erased. They were just appended. So they could be a little bit odd. But the information that was already there um was kept and the information from the spreadsheet was just added to that. Um then there were some that were inactive. But for this the the notes written that's the number.
Jennilyn Tockstein: Mhm.
Emilio Dominguez: Um and we have all you know all the detail here of what happened all the login right notes written. There were some also like inactive customers that I chose to not write because they are inactive but they could uh be useful for them if they get active right. Um so yeah uh three of them defer on on the on the name. So maybe yeah this is open so maybe holding or you can take a look at this right and that's uh that's about
Jennilyn Tockstein: Awesome.
Emilio Dominguez: it th this is from the


00:06:07

Jennilyn Tockstein: Yeah, it looks like most are like inactive customers or they're just not in there and that's
Emilio Dominguez: yeah correct uh yeah
Jennilyn Tockstein: fine.
Emilio Dominguez: some of them were not a complete match also so they weren't they weren't updated the the thing that you asked uh how that screen extraction works, right? Getting that getting the even the statuses. Um I run audits also frequently for the for the data. So there's a tab for that also like either for logic or the numbers like because now we have more data than before when things weren't on production. So I kind of like run some audits. So they are logged here too. Uh I think this wasn't discussed but these are the latest um the latest
Jennilyn Tockstein: Yay.
Emilio Dominguez: um data that we we get from Justin. So he helped me with Kaya and ODF and we fixed also the previous ones because they were they died on on the tokens. So there are some dashboards that are proposed dashboards based on the data.
Jennilyn Tockstein: Awesome.


00:07:43

Emilio Dominguez: Uh and he told me maybe you can spin some things and then maybe Jennilyn could take a look at that. So that's that's that on that those two those two recent Yeah,
Jennilyn Tockstein: Yeah.
Emilio Dominguez: that's uh I I really don't know if this is fresh but I could maybe refresh this but yeah um but they are being uh thrown into big query for that regard. Uh this is what we have already seen from label design the history of work and yeah this is also like very dense but this is more about how the pros work and what they
Jennilyn Tockstein: looking.
Emilio Dominguez: check hourly half an hour what they push and things like that but it's been polished each day because of the new angles that we have for probing proving if other died or data is just way way um is lagging a lot, right? Yeah,
Jennilyn Tockstein: Um,
Emilio Dominguez: that's
Jennilyn Tockstein: so the the label design is going back in because I saw a note from
Emilio Dominguez: Mhm.
Jennilyn Tockstein: Callie saying she was missing some info yesterday,


00:09:09

Emilio Dominguez: Mhm. Yeah. Yeah.
Jennilyn Tockstein: but
Emilio Dominguez: It was a stale because we were they were not battling but live screens were not giving the complete status to the to the workflow about new orders being present and then OBBC was surely very frozen but that was fixed. So yeah, so now those are the the fixes on having multiple multiple angles to check if there are some orders that change on the statuses on the status that they have and push them and update them with more info if if that wasn't a push from the ODBC. OBBC still holds everything. Um, live streams can also get all of that, but you need to teach the teach it where everything is at. So, so yeah. So, I haven't messaged Kelly uh regarding that, but yeah, I was just having a look at the at the board. And I think also the the interface what was quite changed from from Monday on the colors and things like that. But but that's that.
Jennilyn Tockstein: Okay.


00:10:50

Jennilyn Tockstein: Yeah, if you could send her that would be great.
Emilio Dominguez: Mhm. Right.
Jennilyn Tockstein: Um,
Emilio Dominguez: Yeah.
Jennilyn Tockstein: all of this is great. So, I probably made in the Vox scorecards live um set I made a bunch of views based off of the Plex
Emilio Dominguez: Okay.
Jennilyn Tockstein: prods
Emilio Dominguez: All right.
Jennilyn Tockstein: like well what is each part of Rev and Whip, right?
Emilio Dominguez: H.
Jennilyn Tockstein: And I can just combine a few tables and make a view for that. Or um same with like the held inventory. They're like, "Well, what is it?" You know, um I was able to get like a a thing for the sales team to be able to find out where their orders are. I mean, this is not like live.
Emilio Dominguez: Okay.
Jennilyn Tockstein: They could have an eight hour delay, but like
Emilio Dominguez: Yeah, I saw that that one and it was like that's that's good. That's cool. Yeah,
Jennilyn Tockstein: it has been so awesome to have all of the data in there.


00:12:08

Jennilyn Tockstein: Um,
Emilio Dominguez: correct.
Jennilyn Tockstein: one thing that we might end up needing to change that will be an easyish change later is Plex is calling it's putting the container status as expired if it's past the use by date even if it's not past the expiration date. And so that's removing it from inventory valuation and removing it from um being considered on hand. I'm I forced it back into inventory valuation and we may force it back into on hand. I'm not sure.
Emilio Dominguez: Okay.
Jennilyn Tockstein: Um, but it's so nice to have everything in Big Query like fairly fresh to just be able to answer questions because
Emilio Dominguez: Correct.
Jennilyn Tockstein: it's so much easier to work in there than it is to try to look at the Plex screens.
Emilio Dominguez: But I will back up your views because they are custom made, right? So, so they are not tracked right now. So, they are not documented also. So I can just get them get them to the hub uh to have a reference of what they


00:13:16

Jennilyn Tockstein: Awesome.
Emilio Dominguez: have inside uh and if anything just you know a destruction of the project we can get everything from from the backups everything is being backed up everything like credentials everything is uh in a good sense of even if a developer needs to start working on something like okay it's So let's get everything like the container uh the docker right docking container everything that can be spinned on a new laptop. So that's that's good. But I'm going to have a look at those views just to have them as a popup um on a reference on the on the project. Right.
Jennilyn Tockstein: Yeah.
Emilio Dominguez: There was something added on inventory, but let me Yes.
Jennilyn Tockstein: The other thing, my next project I'm I mean I guess it's what Wednesday. So, for sure by next week, if not sooner,
Emilio Dominguez: Mhm.
Jennilyn Tockstein: I'm going to start um trying to get all of the Google Cloud stuff not under me under parasol bisops.
Emilio Dominguez: H.
Jennilyn Tockstein: Um I have an email for it. I'm going to transfer the billing ownership and then the ownership of the projects and then um I'm sure Anony's talked to you about


00:14:51

Emilio Dominguez: All right.
Jennilyn Tockstein: the PCS software. or a project like I want to put I think we'll do a Vox data
Emilio Dominguez: Correct.
Jennilyn Tockstein: lake and a parasol one for like the smaller companies but any of the companies that are big enough to to have their own billing. So, on demand, ship central, um, QSM.
Emilio Dominguez: All
Jennilyn Tockstein: I want to have them each as their own so that we can, um, really easily tell how much they're spending and using each month.
Emilio Dominguez: current.
Jennilyn Tockstein: And also just to kind of keep it clean instead of lumping them into parasol. Um, and then the PCS one needs to be separated because right now Ha's scripts consume more money than the Vox ones, which kind of blows my mind given how much we're doing with the ODBC. Like, I don't know. I I She She added on to some of my scripts um on that
Emilio Dominguez: All right,
Jennilyn Tockstein: sheet and I was looking at it and she has them set to run every 10 minutes. And so I was like, well, that's gonna drive up costs, right?


00:16:01

Jennilyn Tockstein: If you're writing a script every 10 minutes,
Emilio Dominguez: correct.
Jennilyn Tockstein: like all the time
Emilio Dominguez: Yeah. And maybe it's you know the prop logic also like checking if something changed. So that's like pure um you know the essence of how to not spend so much money because if you are just getting everything thrown and not checking if something change uh truthfully right so then it's just maybe sense but each
Jennilyn Tockstein: adds
Emilio Dominguez: scent gets yeah at and then starts so that's also the logic behind some of the things that we have like big things saying okay did we already have this Do we have already this like the full the full table not strike the two million parts or things like that because that's that keeps adding up but surely um they can be well Anthony said that he wanted to start fresh so that's yeah so that's
Jennilyn Tockstein: Yeah.
Emilio Dominguez: something good regarding or not maybe trying to fix or troubleshoot most of the things there but for sure uh the things to separate and also have service accounts.


00:17:13

Emilio Dominguez: But because uh even with just pure turn over uh a developer that has all the
Jennilyn Tockstein: Heat.
Emilio Dominguez: credentials, it's not good, right? It it should be service accounts that hold extraction, the the prop logics that all the things uh that the that the project has. But yeah,
Jennilyn Tockstein: Yeah. And I mean really right now we have the top two. The scripts for Vox can mostly be trashed and then you've got the Parasol marketing one. But the goal is going to be to transfer parasol organization and all projects and the billing account associated with them all out of me.
Emilio Dominguez: H Right on.
Jennilyn Tockstein: get rid of the inactive ones.
Emilio Dominguez: Yeah,
Jennilyn Tockstein: And um
Emilio Dominguez: I can I'm not sure if I have all of those that you have on that, but I can take a look of a look at what what uh the numbers are for me, what the accounts are, and just have them also clean and say, "Okay, so this is this is that right?"
Jennilyn Tockstein: yeah, because I I have a bunch of views in like the box uh scorecards live thing that that aren't used.


00:18:26

Emilio Dominguez: Right. Man,
Jennilyn Tockstein: like their their views of old Netswuite data that's not even getting added to anymore and I think when transferring everything over it'll be a good time to clean up. Um and you know I I tried to explain the importance to to Anthony and Justin like we did this as a trial and then it kind of exploded but it is not good to have everything in my name. like it's going to take me here a week or two to get it all out of my name,
Emilio Dominguez: you're right.
Jennilyn Tockstein: but we don't want everything in my name. Like that's that's not secure.
Emilio Dominguez: correct.
Jennilyn Tockstein: We need we need it in a company name. You know, if I get hit by a bus,
Emilio Dominguez: Yeah,
Jennilyn Tockstein: then it still exists
Emilio Dominguez: let's hope not. But yeah, uh even for the Plex for for example for myself uh those live views those get distracted with my with my account and and most of the things are with my account.
Jennilyn Tockstein: with your Yeah.


00:19:21

Emilio Dominguez: So maybe maybe with Amber is more like uh not so busy just tell her if we have the capabilities to spin service accounts uh in the name of just getting those to extract things and not and just have our own accounts to to do things for ourselves but not the main
Jennilyn Tockstein: Yeah.
Emilio Dominguez: logic or extraction publishing even publishing things right but
Jennilyn Tockstein: Yeah. And with those um I can make them the service accounts.
Emilio Dominguez: All right. Nice.
Jennilyn Tockstein: I think you have to open a case with Plex.
Emilio Dominguez: Uh,
Jennilyn Tockstein: So, we just need the new email. Um, I don't know if we should have everything out of parasol bisops. I kind of like and don't like that idea.
Emilio Dominguez: all right.
Jennilyn Tockstein: It would be nice to have everything consolidated in like one email ownership, but you know, if something ever happened to that account, it'd be really bad.
Emilio Dominguez: Yeah, correct. It is you know like the same for happens for marketing the marketing account at parasol so it holds everything like literally everything so luckily is with Google suite and there are a bunch of ways just to recover that but


00:20:35

Jennilyn Tockstein: Doesn't feel great.
Emilio Dominguez: yeah it's not really uh just split them maybe into three or four areas that could be easily tracked with Soho. Uh, do you have Soho Bolt and do you use that?
Jennilyn Tockstein: I'm I might I'm not sure actually,
Emilio Dominguez: Right on.
Jennilyn Tockstein: fighting.
Emilio Dominguez: Yeah. Yeah, because then then we can also have we could have the set of credentials there even if it's just for ourselves or or for a new dev or whatever, right? Or like you said, even if someone is maybe on a flight, right? and it need something needs to happen and you don't have the credential. You know, you can't access the thing and you need to wait four or five hours to get that and maybe it's just a matter of getting some somewhere very easily but you don't have the access. So that could be taken care by backups uh and where they are and the credentials being shared with so bolt is quite straightforward but I don't really know if you need a seat there and it's paid and yeah but


00:21:54

Jennilyn Tockstein: Yeah, I kind of wonder if it'd be useful to have those paid seats, just one per company and one perisol. Um, and that way the overall Google account could be the the parasol bisops, but each project can have an owner of their company shared with the parasol. That way,
Emilio Dominguez: Correct.
Jennilyn Tockstein: there's two points at any given time if something were to happen for each project. And then that would allow people from those companies to maybe interact, but only be allowed to interact with just their project and not all the projects.
Emilio Dominguez: Yeah, correct. Makes sense.
Jennilyn Tockstein: So,
Emilio Dominguez: Wait.
Jennilyn Tockstein: I know that they like don't like having multiple Google accounts, but I think it is worth it that the nominal cost of those accounts
Emilio Dominguez: Yeah,
Jennilyn Tockstein: is probably worth it for being able to split things up and have that backup.
Emilio Dominguez: correct. Yeah. And the other thing is just also repository. Uh all of that we have worked is also under a repository on parasol group inc.


00:23:04

Emilio Dominguez: I may be the only one to be accessing that right now but that could change even with that the PCS with with the PCS project just to have um it has all Yeah.
Jennilyn Tockstein: That marketing your marketing ones we could divvy up then too, right? Like at these things coming from the marketing email could just be coming from each company's bisops.
Emilio Dominguez: Correct. Yeah. and have some tracking also because of not entirely tickets as some other companies but have the code there have code changes and the way to track that but that's um yeah I might add you to the GitHub repository of this Plex ETL because
Jennilyn Tockstein: Yeah.
Emilio Dominguez: it's like we were discussing it's wood just to have have one person there or sometimes also the executives have the access but they haven't access that like ever so they don't really know how where where is it and how to find it but but yeah that's about
Jennilyn Tockstein: Okay, that's all.
Emilio Dominguez: So yeah, what I'm missing is just those views uh getting those tracked, getting those documented.


00:24:36

Emilio Dominguez: Um I think you are also interacting a little bit with the manual data data app from the app script. Right.
Jennilyn Tockstein: I changed it a fair bit.
Emilio Dominguez: Right. So no worries. Uh I'm I'm I'm aware because I was because of this probe logic and everything I was having some changes done. So there is uh a new deployment like recent deployments there but I got the changes from the most mostly the periods were right on that and right now it has also the new period of six months there. Um and and if it has deviated a a little bit or if you see something odd on that new deployment, just let me know and I can push the change um and track it also. Right.
Jennilyn Tockstein: Okay.
Emilio Dominguez: Yeah. But no worries. I I can
Jennilyn Tockstein: Yeah, I edited the manual table a couple times and um and then the app should override those if she wants to do them. one by one.
Emilio Dominguez: Mhm.
Jennilyn Tockstein: You kind of have to figure out like the amount that would be worth uploading versus just doing them in there.


00:26:00

Jennilyn Tockstein: I'm like, if you have 10 that change, it might just be easier to use the app. You know,
Emilio Dominguez: Correct.
Jennilyn Tockstein: if you have 200, give me a table,
Emilio Dominguez: Yeah,
Jennilyn Tockstein: right?
Emilio Dominguez: definitely.
Jennilyn Tockstein: Like
Emilio Dominguez: Yeah, that's a nice nice idea. Right on. Okay, so any other questions just let me know and I will um tell Kelly about the the new process because they also could see data that is maybe missing on some columns and say hey where is the data? But it it is because um the live screens data could be missing some columns and it can be also made more robust by searching those columns and getting the screens and teaching the bot to to get the screen data and Everything. Right and eventually even even for them OBC wouldn't be useful right it it is very useful for parts and other things that we have discussed because there are thousands of rows and things like that but for label designs it is just very like four or or five order stops for the day it's just more like it can be switched over to to the live screen to the portal to the portal information right if OBBC lacks too much for them right


00:27:36

Jennilyn Tockstein: Okay.
Emilio Dominguez: yeah but I will continue monitoring for today and tomorrow I will have more reference of how all the other VC is reacting and if we can have like all all of the data from the live screens switch can be done the switch can be done All right.
Jennilyn Tockstein: Awesome. Can you send me an email with the web services that you need uh out of your name?
Emilio Dominguez: All right.
Jennilyn Tockstein: Like any anything for um anything that's set up under your name that I need to
Emilio Dominguez: Mhm.
Jennilyn Tockstein: create a new account for and open a case.
Emilio Dominguez: Right on.
Jennilyn Tockstein: Um send that to me and I can get started on that,
Emilio Dominguez: Yeah.
Jennilyn Tockstein: too.
Emilio Dominguez: Nice. Okay, let me get that information and send you the email.
Jennilyn Tockstein: Okay. And then yeah, I'll I'll be coordinating with you as we start that because you're going to have to change stuff out of your name, too.
Emilio Dominguez: Correct. Yeah.
Jennilyn Tockstein: But it's good to do it now before it gets bigger, like as they're starting to give us like we want these scorecards and build this software.
Emilio Dominguez: Yeah.
Jennilyn Tockstein: And it's like, we got to change this or it will be like an unchangeable nightmare.
Emilio Dominguez: Yeah.
Jennilyn Tockstein: So, let's just do it while it's still kind of small.
Emilio Dominguez: in yeah in thousand of places thousand places will be a nightmare but yeah right on okay thank you Jennilyn have a good
Jennilyn Tockstein: Okay, sounds good. Good to see you. Uhhuh. Thanks.
Emilio Dominguez: one goodbye take Yes.
Jennilyn Tockstein: Bye.


Transcription ended after 00:29:19

This editable transcript was computer generated and might contain errors. People can also change the text after it was created.
