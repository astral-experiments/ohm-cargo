    fn is_excluded(&self, manifest_path: &Path) -> bool {
        let matches_path = |path: &String| manifest_path.starts_with(self.root_dir.join(path));
        self.exclude.iter().any(matches_path) && !self.members.iter().flatten().any(matches_path)
    }
