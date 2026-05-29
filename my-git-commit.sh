commit_msg="Commit on $(date '+%Y-%m-%d %H:%M:%S')"

git pull

git add .
git commit -m "$commit_msg"
git push
