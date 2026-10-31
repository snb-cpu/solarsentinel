# Git steps for teammates (do once, then repeat the loop)

## One time
1. Create a free account at github.com and send your username to Sanjay.
2. Accept the invite (email or https://github.com/snb-cpu/solarsentinel/invitations).
3. Install git (https://git-scm.com) and run:
   ```
   git config --global user.name "Your Name"
   git config --global user.email "you@example.com"
   ```
4. Download the project:
   ```
   git clone https://github.com/snb-cpu/solarsentinel.git
   cd solarsentinel
   ```

## Every work session
```
git checkout main
git pull
git checkout -b ui/yourname        # ml/yourname or hw/yourname for the others (first time only)
# ...work ONLY inside your folder...
git add .
git commit -m "what you did"
git push -u origin ui/yourname
```
Then on github.com click "Compare & pull request" -> Create. Sanjay merges it.

## Canva person
Export slides/screens as PNG or PDF (File > Download), put them in `1-ui-design/exports/`, and put the Canva share link in `1-ui-design/README.md`.
