# Runbook: the code host

The owner's steps to give Meter the GitHub App it delivers fixes through, each with the check that
says it worked. P15, FEAT-091, TASK-P15-002. Mapping a Terraform state file to a repository, and the
merge policy, are later P15 tasks and join this file as they are built.

> **Nothing here has been done against a real GitHub yet.** The adapter is written to GitHub's
> published REST reference, API version 2022-11-28, and tested against recorded shapes. Expect the
> first run of each step to find something, and record it in `tasks/ISSUES.md` as it happens.

## The GitHub App

Meter delivers each fix as a pull request through a GitHub App the organization registers and
installs, OPEN-13. For each request the worker signs a token with the app's private key, valid for
ten minutes, and exchanges it for an installation token narrowed to the one repository and to what
the request needs; it keeps neither. The key is read from Secrets Manager under
`meter/<env>/codehost/` when a request is about to be made, and is never printed, logged or stored
anywhere else. Only the worker reaches GitHub, through the NAT gateway, ADR-0036.

| # | Step | Check |
| --- | --- | --- |
| 1 | An organization owner registers a GitHub App under the organization's Developer settings, with no webhook and these repository permissions: Contents and Pull requests, read and write; Checks, Commit statuses and Metadata, read | The app's page shows its App ID |
| 2 | Generate a private key on the app's page; GitHub downloads it as a `.pem` file | The page lists the key's fingerprint |
| 3 | Install the app on the organization, choosing only the repositories holding Terraform that Meter may propose changes to | The installation lists those repositories |
| 4 | Store the key in the hub account under the code host path, from the file, and delete the file afterwards | `aws secretsmanager describe-secret --secret-id meter/dev/codehost/github-app` answers |
| 5 | First contact with the app, below | GitHub's line reads `answered` |

Step 4, with the key in `meter.private-key.pem`:

```bash
aws secretsmanager create-secret --name meter/dev/codehost/github-app --secret-string file://meter.private-key.pem
```

Step 5, with credentials for the hub account and `AWS_REGION` set to the hub's Region:

```bash
make first-contact ENV=dev ACCOUNT=<a member account id> REGION=<a Region it uses> CODEHOST_SECRET=meter/dev/codehost/github-app CODEHOST_APP_ID=<the App ID> CODEHOST_REPOSITORY=<owner/name>
```

It signs the app's token, asks GitHub which installation holds the repository, and lists the
installation's repositories with a token that may read their metadata and nothing else. It writes
nothing. GitHub is not read unless all three are named, and the report says so.

| What the check says | What it means | What to do |
| --- | --- | --- |
| `Misconfigured`, not under the code host path | The secret's name does not start `meter/<env>/codehost/` | Store it under that path; the task role may read nothing else |
| `Misconfigured`, no secret named | The secret does not exist in the hub account and Region | Step 4 in the hub account |
| `Misconfigured`, not a private key in PEM form | The secret holds something other than the downloaded key | Step 4 with the `.pem` file's whole contents |
| `Misconfigured`, not installed on | The app is not installed on the repository, or the repository does not exist | Step 3, adding the repository |
| `Misconfigured`, would not grant | The app was registered without a permission Meter asks for | Step 1's permissions, then approve them on the installation |
| `AccessDenied`, refused the app's credential | The App ID is wrong, or the key was deleted from the app | Check the App ID; a new key, step 2 |
| `Throttled` | GitHub's rate limit is spent | Nothing; the next run asks again |
| `Unreachable` | GitHub did not answer | Check the worker's route to the internet, ADR-0036 |
| `SchemaDrift` | GitHub answered in a shape the adapter does not know | Record it with the field it names |
