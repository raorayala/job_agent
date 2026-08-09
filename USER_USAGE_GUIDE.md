# User Usage Guide — Local AI Job Search Agent

A private, local-first personal career assistant.

---

## Quick Reference Workflow

```powershell
# 1. Start local capture server for 1-click Chrome bookmarklet
python -m job_agent serve

# 2. Open automated search query links tailored to your config.yaml skills (posted in last 1-2 weeks)
python -m job_agent search-links --open --browser chrome

# 3. Direct search and fetch from job platforms (<10 jobs per platform, posted in last 1-2 weeks)
python -m job_agent fetch-jobs --platforms dice,ziprecruiter --limit 9

# 4. Sync job alert emails from Gmail (received in last 14 days)
python -m job_agent sync-gmail

# 5. Re-score all jobs against your master resume text and profile
python -m job_agent analyze

# 6. List high-matching opportunities
python -m job_agent jobs --min-score 60

# 7. Generate ATS tailored DOCX resume & cover letter
python -m job_agent tailor <job_id>

# 8. Mark as applied after manual submission
python -m job_agent mark-applied <job_id> --confirm

# 9. View search pipeline dashboard & follow-ups
python -m job_agent dashboard
python -m job_agent follow-ups
```

---

## 1-Click Chrome Bookmarklet Setup

1. Run `python -m job_agent serve` in terminal.
2. In Google Chrome, press `Ctrl + Shift + B` to show Bookmarks Bar.
3. Right-click Bookmarks Bar -> **Add page...**
   - **Name**: `Capture Job`
   - **URL**:
```javascript
javascript:(function(){
  const title = document.querySelector('h1')?.innerText || document.title;
  const company = document.querySelector('[data-testid="inlineHeader-companyName"], .companyName, .company-name, [data-cy="search-result-company-name"]')?.innerText || "Unknown";
  const url = window.location.href;
  const description = document.querySelector('#jobDescriptionText, .job-description, .description, #job-description')?.innerText || document.body.innerText.slice(0, 3000);

  fetch('http://localhost:8000/capture', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({title, company, url, description})
  })
  .then(res => res.json())
  .then(data => alert(`✅ Job Saved to Job Agent!\n\nID: #${data.job_id}\nTitle: ${data.title}\nCompany: ${data.company}\nMatch Score: ${data.score}/100`))
  .catch(err => alert('❌ Error: Make sure "python -m job_agent serve" is running in terminal.'));
})();
```
4. Click **`Capture Job`** on Chrome's bar while viewing any job on Indeed, Dice, ZipRecruiter, Glassdoor, or LinkedIn!

---

## 🚀 Key Feature Highlights

### 1. Initial Batch Constraints & Freshness Filter
- **Batch Size Limit**: `fetch-jobs` defaults to **9 items per platform** (< 10 jobs per run) to ensure focused, manageable initial reviews.
- **1–2 Week Freshness**: All generated search links (`search-links`) and direct fetch queries (`fetch-jobs`) filter specifically for jobs posted within the **last 1 to 2 weeks** (14 days max).
- **Chrome Launching**: Running `search-links --open --browser chrome` explicitly launches Google Chrome on Windows, bypassing Edge browser routing.

---

## 📖 Complete Command Reference

For a full reference of all available CLI commands, options, and parameters, please see the **[CLI Command Cheat Sheet](CLI_CHEAT_SHEET.md)**.
