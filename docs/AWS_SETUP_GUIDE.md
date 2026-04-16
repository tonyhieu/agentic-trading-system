# AWS Setup Guide for Strategy Snapshot System

This guide provides step-by-step instructions to set up AWS infrastructure for the automated strategy snapshot system.

## Prerequisites
- Credit/debit card for AWS account verification
- Email address for AWS account
- Access to this GitHub repository settings

---

## Step 1: Create AWS Account

### 1.1 Sign Up for AWS
1. Go to https://aws.amazon.com/
2. Click **"Create an AWS Account"** (top right)
3. Enter your email address and choose an AWS account name (e.g., "agentic-trading-snapshots")
4. Click **"Verify email address"**
5. Check your email and enter the verification code
6. Create a strong root password and click **"Continue"**

### 1.2 Add Contact Information
1. Select account type: **"Personal"** (unless you have a business)
2. Fill in your contact information (name, phone, address)
3. Read and accept the AWS Customer Agreement
4. Click **"Continue"**

### 1.3 Add Payment Information
1. Enter your credit/debit card information
2. Enter billing address
3. Click **"Verify and Continue"**
4. You may see a $1 temporary authorization charge (refunded automatically)

### 1.4 Verify Identity
1. Choose verification method (Text message or Voice call)
2. Enter your phone number
3. Enter the verification code you receive
4. Click **"Continue"**

### 1.5 Choose Support Plan
1. Select **"Basic support - Free"** (sufficient for this project)
2. Click **"Complete sign up"**

### 1.6 Sign In to AWS Console
1. Wait for account activation email (usually takes a few minutes)
2. Go to https://console.aws.amazon.com/
3. Sign in with your root email and password
4. **Important:** Enable MFA (Multi-Factor Authentication) on root account:
   - Click your account name (top right) → Security credentials
   - Under "Multi-factor authentication (MFA)", click "Assign MFA device"
   - Follow the prompts to set up virtual MFA (use Google Authenticator or similar app)

---

## Step 2: Create IAM User for GitHub Actions

**Why:** Never use root account credentials for applications. Create a dedicated IAM user with minimal permissions.

### 2.1 Navigate to IAM
1. In AWS Console, search for **"IAM"** in the top search bar
2. Click **"IAM"** to open the Identity and Access Management dashboard
3. Click **"Users"** in the left sidebar
4. Click **"Create user"** button

### 2.2 Create User
1. **User name:** `github-actions-snapshot-uploader`
2. **Do NOT** check "Provide user access to the AWS Management Console"
3. Click **"Next"**

### 2.3 Set Permissions (we'll add these after creating the bucket)
1. Select **"Attach policies directly"**
2. **Don't attach any policies yet** - we'll create a custom policy after the bucket exists
3. Click **"Next"**
4. Click **"Create user"**

### 2.4 Create Access Keys
1. Click on the newly created user: `github-actions-snapshot-uploader`
2. Click the **"Security credentials"** tab
3. Scroll down to **"Access keys"** section
4. Click **"Create access key"**
5. Select use case: **"Application running outside AWS"**
6. Click **"Next"**
7. (Optional) Add description tag: "GitHub Actions snapshot upload"
8. Click **"Create access key"**

### 2.5 Save Credentials Securely
⚠️ **CRITICAL:** This is the ONLY time you'll see the secret access key!

1. **Download .csv file** or copy both values:
   - Access key ID (looks like: `AKIAIOSFODNN7EXAMPLE`)
   - Secret access key (looks like: `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY`)
2. Store these in a secure location (password manager)
3. **Never commit these to git or share them publicly**
4. Click **"Done"**

---

## Step 3: Create S3 Bucket

### 3.1 Navigate to S3
1. In AWS Console search bar, type **"S3"**
2. Click **"S3"** to open the Amazon S3 dashboard
3. Click **"Create bucket"** button

### 3.2 Configure Bucket Basics
1. **Bucket name:** `agentic-trading-snapshots-<unique-suffix>`
   - Example: `agentic-trading-snapshots-uchicago-2026`
   - Must be globally unique across all AWS
   - Must be lowercase, no spaces
2. **AWS Region:** Choose closest to you for best performance:
   - `us-east-1` (N. Virginia) - common default
   - `us-west-2` (Oregon) - west coast
   - `eu-west-1` (Ireland) - Europe
3. Keep note of your region - you'll need it later

### 3.3 Object Ownership
1. Select **"ACLs disabled (recommended)"**
2. This ensures only your account can access objects

### 3.4 Block Public Access Settings
⚠️ **IMPORTANT:** Keep all public access blocked for security

1. **Keep checked:** "Block all public access"
2. All four checkboxes under it should be checked
3. This prevents accidental public exposure of trading strategies

### 3.5 Bucket Versioning
1. Select **"Disable"** (we're using timestamped snapshots instead)

### 3.6 Default Encryption
1. Select **"Enable"** under Server-side encryption
2. Choose **"Amazon S3 managed keys (SSE-S3)"** (free, sufficient security)

### 3.7 Advanced Settings
1. **Object Lock:** Leave disabled
2. Click **"Create bucket"**

### 3.8 Verify Bucket Created
1. You should see your bucket in the list
2. Click on the bucket name to open it
3. It should be empty - that's correct!

---

## Step 4: Configure S3 Lifecycle Policy (30-day retention)

### 4.1 Navigate to Lifecycle Rules
1. Open your bucket: `agentic-trading-snapshots-<your-suffix>`
2. Click the **"Management"** tab
3. Scroll to **"Lifecycle rules"** section
4. Click **"Create lifecycle rule"**

### 4.2 Configure Lifecycle Rule
1. **Lifecycle rule name:** `delete-old-snapshots-30-days`
2. **Choose rule scope:** Select "Apply to all objects in the bucket"
3. Check the box: "I acknowledge that this rule will apply to all objects in the bucket"

### 4.3 Lifecycle Rule Actions
1. Check **"Expire current versions of objects"**
2. Under "Expire current versions of objects":
   - **Days after object creation:** `30`
3. Leave other options unchecked

### 4.4 Review and Create
1. Review the rule summary:
   - Should say: "Current versions of objects will expire 30 days after creation"
2. Click **"Create rule"**
3. Verify the rule appears in the Lifecycle rules list with status "Enabled"

---

## Step 5: Create IAM Policy for S3 Access

### 5.1 Navigate to IAM Policies
1. Go back to **IAM** service (search bar → IAM)
2. Click **"Policies"** in the left sidebar
3. Click **"Create policy"** button

### 5.2 Create Policy Using JSON
1. Click the **"JSON"** tab (not Visual editor)
2. Replace all content with the following policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowSnapshotUpload",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::agentic-trading-snapshots-<your-suffix>",
        "arn:aws:s3:::agentic-trading-snapshots-<your-suffix>/*"
      ]
    }
  ]
}
```

3. **IMPORTANT:** Replace `<your-suffix>` with your actual bucket name
   - Example: `arn:aws:s3:::agentic-trading-snapshots-uchicago-2026`
4. Click **"Next"**

### 5.3 Name and Create Policy
1. **Policy name:** `GitHubActionsSnapshotUploadPolicy`
2. **Description:** "Minimal permissions for GitHub Actions to upload strategy snapshots to S3"
3. Click **"Create policy"**

---

## Step 6: Attach Policy to IAM User

### 6.1 Navigate to Your IAM User
1. In IAM dashboard, click **"Users"** in left sidebar
2. Click on **`github-actions-snapshot-uploader`**
3. Click **"Add permissions"** button
4. Select **"Attach policies directly"**

### 6.2 Attach the Policy
1. In the search box, type: `GitHubActionsSnapshotUploadPolicy`
2. Check the box next to your policy
3. Click **"Next"**
4. Click **"Add permissions"**

### 6.3 Verify Permissions
1. Click the **"Permissions"** tab
2. You should see `GitHubActionsSnapshotUploadPolicy` listed
3. Click on the policy name to verify it shows the correct S3 bucket ARN

---

## Step 7: Add Credentials to GitHub Repository Secrets

### 7.1 Navigate to GitHub Repository Settings
1. Go to your GitHub repository: https://github.com/<your-username>/agentic-trading-system
2. Click **"Settings"** tab (top navigation)
3. In left sidebar, expand **"Security"** section
4. Click **"Secrets and variables"** → **"Actions"**

### 7.2 Add AWS Access Key ID
1. Click **"New repository secret"** button
2. **Name:** `AWS_ACCESS_KEY_ID`
3. **Secret:** Paste your Access Key ID (from Step 2.5)
   - Should look like: `AKIAIOSFODNN7EXAMPLE`
4. Click **"Add secret"**

### 7.3 Add AWS Secret Access Key
1. Click **"New repository secret"** button again
2. **Name:** `AWS_SECRET_ACCESS_KEY`
3. **Secret:** Paste your Secret Access Key (from Step 2.5)
   - Should look like: `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY`
4. Click **"Add secret"**

### 7.4 Add AWS Region
1. Click **"New repository secret"** button again
2. **Name:** `AWS_REGION`
3. **Secret:** Your bucket's region (from Step 3.2)
   - Example: `us-east-1` or `us-west-2`
4. Click **"Add secret"**

### 7.5 Add S3 Bucket Name
1. Click **"New repository secret"** button again
2. **Name:** `S3_BUCKET_NAME`
3. **Secret:** Your full bucket name
   - Example: `agentic-trading-snapshots-uchicago-2026`
4. Click **"Add secret"**

### 7.6 Verify All Secrets
You should now have 4 repository secrets:
- ✅ `AWS_ACCESS_KEY_ID`
- ✅ `AWS_SECRET_ACCESS_KEY`
- ✅ `AWS_REGION`
- ✅ `S3_BUCKET_NAME`

---

## Step 8: Set Up AWS Budget Alert (Optional but Recommended)

### 8.1 Navigate to Billing
1. Click your account name (top right) → **"Billing and Cost Management"**
2. In left sidebar, click **"Budgets"**
3. Click **"Create budget"**

### 8.2 Configure Budget
1. **Budget setup:** Select **"Use a template"**
2. Choose **"Monthly cost budget"**
3. **Budget name:** `snapshot-system-budget`
4. **Budgeted amount:** `$15.00` (adjust based on your needs)
5. **Email recipients:** Enter your email address
6. Click **"Create budget"**

### 8.3 Verify Alert
1. You should receive a confirmation email
2. You'll be notified if costs exceed 85% and 100% of budget

---

## ✅ Setup Complete!

You now have:
- ✅ AWS account with MFA enabled
- ✅ S3 bucket with 30-day lifecycle policy
- ✅ IAM user with minimal permissions
- ✅ GitHub repository secrets configured
- ✅ Budget alert (optional)

### What You've Created:

**Bucket Name:** `agentic-trading-snapshots-<your-suffix>`
**Region:** (e.g., us-east-1)
**IAM User:** `github-actions-snapshot-uploader`
**Lifecycle Policy:** Auto-delete after 30 days

### Record These Values (you'll need them):
- Bucket name: `agentic-trading-snapshots-<your-suffix>`
- AWS Region: `us-east-1` (or your chosen region)
- Access Key ID: Stored in GitHub Secrets
- Secret Access Key: Stored in GitHub Secrets

---

## Next Steps

Now that AWS infrastructure is ready, you can proceed with:
1. Creating the GitHub Actions workflow (`.github/workflows/snapshot-strategy.yml`)
2. Creating SKILLS.md documentation for agents
3. Testing the snapshot system
4. Implementing the rest of the plan

**Ready for autopilot mode!** 🚀

---

## Troubleshooting

### Issue: "Bucket name already exists"
- Bucket names are globally unique across all AWS accounts
- Try adding a more specific suffix: `-uchicago-2026-<your-initials>`

### Issue: "Access denied" when testing
- Verify IAM policy has correct bucket ARN
- Verify GitHub secrets are spelled exactly right (case-sensitive)
- Check that policy is attached to the IAM user

### Issue: "Credentials not working"
- Regenerate access keys in IAM
- Update GitHub secrets with new keys
- Ensure you copied the entire key (no spaces or line breaks)

### Issue: Cost concerns
- Check AWS Cost Explorer (Billing dashboard)
- Verify lifecycle policy is enabled and working
- Consider reducing retention to 7-14 days if needed

---

## Cost Breakdown

**Expected monthly costs:**
- S3 Storage (100GB): ~$2.30
- PUT requests (500/month): ~$0.003
- GET requests (occasional): ~$0.001
- Data transfer out: $0 (uploads are free)

**Total: ~$3-5/month** for moderate usage

This is well within the $10-50/month budget!
