#!/usr/bin/env python3
"""Behind the Bastards Podcast Episode Downloader

This script downloads episode information and transcripts from the
"Behind the Bastards" podcast API and saves them to individual files.

Vibe coded with Claude 3.7 Sonnet.

Usage:
  btb_downloader.py [--output-dir=<dir>] [--delay=<seconds>] [--limit=<count>]
  btb_downloader.py (-h | --help)
  btb_downloader.py --version

Options:
  -h --help           Show this help message and exit.
  --version           Show version.
  --output-dir=<dir>  Directory to save episode files [default: episodes].
  --delay=<seconds>   Delay between requests in seconds [default: 1].
  --limit=<count>     Limit number of episodes to download [default: 10].

"""
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from docopt import docopt


class EpisodeDownloader:
    """Class to download Behind the Bastards podcast episodes."""

    BASE_URL = "https://www.iheart.com/podcast/105-behind-the-bastards-29236323/"
    API_BASE_URL = "https://us.api.iheart.com/api/v3/podcast/podcasts/29236323/episodes"
    USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    VERSION = "1.3.7"  # Script version

    def __init__(
        self, output_dir: str = "episodes", delay: int = 1, limit: int = 10
    ) -> None:
        """Initialize the EpisodeDownloader.

        Args:
            output_dir: Directory to save episode files.
            delay: Delay between requests in seconds.
            limit: Maximum number of episodes to download.
        """
        self.output_dir = output_dir
        self.delay = delay
        self.limit = limit
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://www.iheart.com",
            "Referer": "https://www.iheart.com/",
        })
        self._create_output_dir()
        self.existing_episodes, self.outdated_episodes = self._get_existing_episodes()

    def _create_output_dir(self) -> None:
        """Create the output directory if it doesn't exist."""
        os.makedirs(self.output_dir, exist_ok=True)

    def _get_existing_episodes(self) -> Tuple[Set[str], Set[str]]:
        """Get the set of episode URLs that have already been downloaded.

        Returns:
            A tuple containing (existing_episodes, outdated_episodes):
            - existing_episodes: Set of episode URLs that have been downloaded
            - outdated_episodes: Set of episode URLs that need to be re-downloaded
              due to version change
        """
        existing_episodes = set()
        outdated_episodes = set()

        for file_path in Path(self.output_dir).glob("*.txt"):
            with open(file_path, "r", encoding="utf-8") as f:
                url = None
                version = None

                for line in f:
                    if line.startswith("URL: "):
                        url = line[5:].strip()
                    elif line.startswith("BTB Downloader Version: "):
                        version = line[23:].strip()

                    if url and version:
                        break

                if url:
                    existing_episodes.add(url)
                    # If version is missing or different, add to outdated episodes
                    if version != self.VERSION:
                        outdated_episodes.add(url)

        return existing_episodes, outdated_episodes

    def _slugify(self, text: str) -> str:
        """Convert text to URL slug.

        Args:
            text: The text to convert.

        Returns:
            A URL-friendly slug.
        """
        # Convert to lowercase
        text = text.lower()
        # Replace non-alphanumeric with hyphens
        text = re.sub(r'[^a-z0-9]+', '-', text)
        # Remove leading/trailing hyphens
        text = text.strip('-')
        # Collapse multiple hyphens
        text = re.sub(r'-+', '-', text)
        return text

    def _build_episode_url(self, episode: Dict[str, Any]) -> str:
        """Build episode URL from episode data.

        Args:
            episode: The episode data dictionary.

        Returns:
            The episode URL.
        """
        podcast_slug = episode.get('podcastSlug', '105-behind-the-bastards')
        podcast_id = episode.get('podcastId', 29236323)
        episode_id = episode.get('id')
        title = episode.get('title', '')
        title_slug = self._slugify(title)

        return f"https://www.iheart.com/podcast/{podcast_slug}-{podcast_id}/episode/{title_slug}-{episode_id}/"

    def _format_date(self, timestamp_ms: int) -> str:
        """Convert a timestamp in milliseconds to a formatted date string.

        Args:
            timestamp_ms: The timestamp in milliseconds.

        Returns:
            A formatted date string.
        """
        try:
            dt = datetime.fromtimestamp(timestamp_ms / 1000)
            return dt.strftime("%B %d, %Y")
        except (ValueError, TypeError, OverflowError):
            return "Unknown Date"

    def _format_date_for_filename(self, timestamp_ms: int) -> str:
        """Convert a timestamp in milliseconds to YYYY-MM-DD format.

        Args:
            timestamp_ms: The timestamp in milliseconds.

        Returns:
            The date in YYYY-MM-DD format, or "Unknown-Date" if parsing fails.
        """
        try:
            dt = datetime.fromtimestamp(timestamp_ms / 1000)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError, OverflowError):
            return "Unknown-Date"

    def _safe_filename(self, episode: Dict[str, Any]) -> str:
        """Create a safe filename from the episode data.

        Args:
            episode: The episode data dictionary.

        Returns:
            A safe filename for the episode.
        """
        # Get the title slug
        title = episode.get('title', 'Unknown')
        title_slug = self._slugify(title)

        # Get formatted date
        timestamp_ms = episode.get('startDate', 0)
        formatted_date = self._format_date_for_filename(timestamp_ms)

        # Create safe filename
        return f"{formatted_date}_{title_slug}.txt"

    def _get_episode_list(self) -> List[Dict[str, Any]]:
        """Fetch the list of episodes using the iHeart API.

        Returns:
            A list of episode data dictionaries.
        """
        all_episodes = []
        filtered_episodes = []
        page_key = None
        api_limit = 20  # We can request more per call than the UI shows

        print("Fetching episode list from API...")

        # Continue fetching until we have enough episodes or there are no more
        while len(filtered_episodes) < self.limit:
            # Prepare API URL with page_key if available
            if page_key:
                url = f"{self.API_BASE_URL}?newEnabled=false&limit={api_limit}&pageKey={quote(page_key)}&sortBy=startDate-desc"
            else:
                url = f"{self.API_BASE_URL}?newEnabled=false&limit={api_limit}&sortBy=startDate-desc"

            print(f"Fetching episodes batch (total so far: {len(all_episodes)})")

            # Make API request
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()

            # Extract episodes
            batch_episodes = data.get("data", [])
            if not batch_episodes:
                print("No more episodes available in API")
                break

            all_episodes.extend(batch_episodes)

            # Filter for BTB episodes
            filtered_episodes = [
                episode for episode in all_episodes
                if "it could happen here" not in episode.get("title", "").lower()
            ]

            print(f"Found {len(filtered_episodes)} Behind the Bastards episodes so far")

            # Check if we should continue
            page_key = data.get("pageKey")
            # Also check links.next which is used in the API response
            if not page_key and "links" in data and "next" in data["links"]:
                page_key = data["links"]["next"]

            if not page_key:
                print("No more pages available in API")
                break

            # Respect the delay between requests
            time.sleep(self.delay)

        print(f"Found {len(all_episodes)} total episodes from API")
        print(f"Filtered to {len(filtered_episodes)} Behind the Bastards episodes")

        # Return only the episodes we need
        return filtered_episodes[:self.limit]

    def _extract_transcript(self, soup: BeautifulSoup) -> str:
        """Extract the episode transcript from the page.

        Args:
            soup: The BeautifulSoup object for the episode page.

        Returns:
            The episode transcript.
        """
        # Find the transcript section
        transcript_section = soup.find("div", id="transcription")
        if not transcript_section:
            # Try alternative selectors
            transcript_section = soup.find("div", class_=lambda c: c and "transcription" in c.lower())

        if not transcript_section:
            return "No transcript available."

        transcript_lines = []
        current_speaker = None
        new_speaker_found = False

        # Find all spans in order
        all_spans = transcript_section.find_all("span")

        # Process each span
        for span in all_spans:
            span_class = span.get("class", [])
            span_class_str = " ".join(span_class)

            # Check span type
            if "podcast-transcription-speaker" in span_class_str:
                current_speaker = span.text.strip()
                new_speaker_found = True

            elif "podcast-transcription-time" in span_class_str:
                timestamp = span.text.strip()

                if new_speaker_found and current_speaker:
                    # New speaker with timestamp
                    if transcript_lines:  # Add a blank line before new speaker
                        transcript_lines.append("\n")
                    transcript_lines.append(f"{current_speaker} {timestamp}:")
                    new_speaker_found = False
                elif current_speaker:
                    # Continuing speaker with new timestamp
                    # Create whitespace of same length as speaker name
                    if transcript_lines:  # Add a blank line before new timestamp
                        transcript_lines.append("\n")
                    whitespace = " " * len(current_speaker)
                    transcript_lines.append(f"{whitespace} {timestamp}:")
                else:
                    # No speaker context
                    if transcript_lines:  # Add a blank line
                        transcript_lines.append("\n")
                    transcript_lines.append(f"Speaker {timestamp}:")

            elif "podcast-transcription-text" in span_class_str:
                # Add text
                text = span.text.strip()
                if text:
                    if transcript_lines and transcript_lines[-1].endswith(":"):
                        # First line after speaker/timestamp
                        transcript_lines.append(f"\n{text}")
                    else:
                        # Continuation line - check if we need a space
                        if transcript_lines and not transcript_lines[-1].endswith("\n"):
                            transcript_lines.append(f" {text}")
                        else:
                            transcript_lines.append(text)

        # Join all transcript lines
        transcript = "".join(transcript_lines).strip()

        # Clean up empty lines (more than 2 consecutive newlines)
        transcript = re.sub(r'\n{3,}', '\n\n', transcript)

        # Make sure there's a line break after each speaker block
        transcript = re.sub(r'([^.\n])\n([A-Z][a-z]+)', r'\1\n\n\2', transcript)

        return transcript if transcript else "No transcript available."

    def _get_soup(self, url: str) -> BeautifulSoup:
        """Get a BeautifulSoup object for the given URL.

        Args:
            url: The URL to get the soup for.

        Returns:
            A BeautifulSoup object for the given URL.
        """
        response = self.session.get(url)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    def _clean_html_description(self, html_description: str) -> str:
        """Clean HTML from description and remove privacy notice.

        Args:
            html_description: The HTML description string.

        Returns:
            A clean plain text description.
        """
        # Parse the HTML
        soup = BeautifulSoup(html_description, "html.parser")

        # Remove privacy information paragraph
        for p in soup.find_all("p"):
            if p.find("a", href=lambda href: href and "omnystudio.com/listener" in href):
                p.decompose()

        # Return plain text
        return soup.get_text().strip()

    def _extract_summary_and_transcript(self, url: str, html_description: str) -> Tuple[str, str]:
        """Extract the summary and transcript.

        Args:
            url: The URL of the episode page.
            html_description: The HTML description from the API.

        Returns:
            A tuple containing (summary, transcript).
        """
        # Clean the description from the API
        summary = self._clean_html_description(html_description)

        # Get the page and extract transcript
        soup = self._get_soup(url)
        transcript = self._extract_transcript(soup)

        return summary, transcript

    def _save_episode(self, episode: Dict[str, Any], summary: str, transcript: str) -> None:
        """Save the episode information to a file.

        Args:
            episode: The episode data from the API.
            summary: The episode summary.
            transcript: The episode transcript.
        """
        # Extract data from the API response
        title = episode.get("title", "Unknown Title")
        timestamp_ms = episode.get("startDate", 0)
        formatted_date = self._format_date(timestamp_ms)
        length = f"{episode.get('duration', 0) // 60} mins"
        url = self._build_episode_url(episode)

        filename = self._safe_filename(episode)
        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"Title: {title}\n")
            f.write(f"Date: {formatted_date}\n")
            f.write(f"Length: {length}\n")
            f.write(f"URL: {url}\n")
            f.write(f"BTB Downloader Version: {self.VERSION}\n")
            f.write(f"Summary: {summary}\n\n")
            f.write("TRANSCRIPT:\n\n")
            f.write(transcript)

        print(f"Saved episode: {title}")

    def download_episodes(self) -> None:
        """Download episodes from the podcast API."""
        print("Starting episode download...")
        print(f"BTB Downloader Version: {self.VERSION}")

        # Get episode list from API (already filtered and limited)
        btb_episodes = self._get_episode_list()

        print(f"Working with {len(btb_episodes)} Behind the Bastards episodes (limit: {self.limit}).")

        # Identify episodes to download
        episodes_to_download = []
        for episode in btb_episodes:
            episode_url = self._build_episode_url(episode)

            # Include if not downloaded or needs update due to version change
            if (episode_url not in self.existing_episodes or
                    episode_url in self.outdated_episodes):
                episodes_to_download.append(episode)

        print(f"Found {len(episodes_to_download)} episodes to download/update.")

        # Process each episode
        downloaded_count = 0
        for i, episode in enumerate(btb_episodes):
            episode_url = self._build_episode_url(episode)

            # Skip already downloaded episodes (unless they need to be updated)
            if episode_url in self.existing_episodes and episode_url not in self.outdated_episodes:
                print(f"Skipping already downloaded episode {i+1}/{len(btb_episodes)}: {episode.get('title')}")
                continue

            if episode_url in self.outdated_episodes:
                print(f"Updating outdated episode {i+1}/{len(btb_episodes)}: {episode.get('title')}")
            else:
                print(f"Processing new episode {i+1}/{len(btb_episodes)}: {episode.get('title')}")

            try:
                # Get summary and transcript
                summary, transcript = self._extract_summary_and_transcript(
                    episode_url,
                    episode.get("description", "")
                )

                # Save the episode information
                self._save_episode(episode, summary, transcript)

                # Update tracking sets
                self.existing_episodes.add(episode_url)
                if episode_url in self.outdated_episodes:
                    self.outdated_episodes.remove(episode_url)

                downloaded_count += 1

                # Throttle requests
                if i < len(btb_episodes) - 1:
                    time.sleep(self.delay)

            except Exception as e:
                print(f"Error processing episode {episode_url}: {e}")


def main() -> None:
    """Main function to run the script."""
    arguments = docopt(__doc__, version=f"Behind the Bastards Downloader {EpisodeDownloader.VERSION}")

    output_dir = arguments["--output-dir"]
    delay = float(arguments["--delay"])
    limit = int(arguments["--limit"])

    downloader = EpisodeDownloader(output_dir=output_dir, delay=delay, limit=limit)
    downloader.download_episodes()


if __name__ == "__main__":
    main()
