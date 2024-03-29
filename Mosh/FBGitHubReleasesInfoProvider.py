#!/usr/bin/python
#
# Copyright (c) Facebook, Inc. and its affiliates.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.#
# This was originally written by Tim Sutton under the Apache license, and has
# been slightly modified to accommodate minor logic changes:
# https://github.com/autopkg/autopkg/blob/master/Code/autopkglib/GitHubReleasesInfoProvider.py
#


"""See docstring for FBGitHubReleasesInfoProvider class"""

# Disabling warnings for env members and imports that only affect recipe-
# specific processors.
# pylint: disable=e1101,f0401

import re
import urllib2

import autopkglib.github
from autopkglib import Processor, ProcessorError

__all__ = ["FBGitHubReleasesInfoProvider"]


class FBGitHubReleasesInfoProvider(Processor):
  # pylint: disable=missing-docstring
  description = ("Get metadata from the latest release from a GitHub project"
                 " using the GitHub Releases API.")
  input_variables = {
      "asset_regex": {
          "required": False,
          "description": ("If set, return only a release asset that "
                          "matches this regex.")
      },
      "github_repo": {
          "required": True,
          "description": ("Name of a GitHub user and repo, ie. "
                          "'MagerValp/AutoDMG'")
      },
      "include_prereleases": {
          "required": False,
          "description": ("If set to True or a non-empty value, include "
                          "prereleases.")
      },
      "sort_by_highest_tag_names": {
          "required": False,
          "description": ("Set this to have releases sorted by highest "
                          "to lowest tag version. By default, releases "
                          "are sorted descending by date posted. This "
                          "changes this behavior for cases where an 'older' "
                          "release may be posted later.")
      },
  }
  output_variables = {
      "release_notes": {
          "description": ("Full release notes body text from the chosen "
                          "release.")
      },
      "url": {
          "description": ("URL for the first asset found for the project's "
                          "latest release.")
      },
      "version": {
          "description": ("Version info parsed, naively derived from the "
                          "release's tag.")
      },
  }

  __doc__ = description

  def get_releases(self, repo):
    """Return a list of releases dicts for a given GitHub repo. repo must
    be of the form 'user/repo'"""
    # pylint: disable=no-self-use
    releases = None
    github = autopkglib.github.GitHubSession()
    releases_uri = "/repos/%s/releases" % repo
    try:
      (releases, status) = github.call_api(releases_uri)
    # Catch a 404
    except urllib2.HTTPError as err:
      raise ProcessorError("GitHub API returned an error: '%s'." % err)
    if status != 200:
      raise ProcessorError(
          "Unexpected GitHub API status code %s." % status)

    if not releases:
      raise ProcessorError("No releases found for repo '%s'" % repo)

    return releases

  def select_asset(self, releases, regex):
    """Iterates through the releases in order and determines the first
    eligible asset that matches the criteria. Sets the selected release
    and asset data in class variables.
    - Release 'type' depending on whether 'include_prereleases' is set
    - If 'asset_regex' is set, whether the asset's 'name' (the filename)
      matches the regex. If not, then the first asset will be
      returned."""
    selected = None
    for rel in releases:
      if selected:
        break
      if rel["prerelease"] and not self.env.get("include_prereleases"):
        continue

      assets = rel.get("assets")
      if not assets:
        continue

      for asset in assets:
        if not regex:
          selected = (rel, asset)
          break
        else:
          if re.match(regex, asset["name"]):
            self.output("Matched regex '%s' among asset(s): %s" % (
                regex,
                ", ".join([x["name"] for x in assets])))
            selected = (rel, asset)
            break
    if not selected:
      raise ProcessorError(
          "No release assets were found that satisfy the criteria.")

    # pylint: disable=w0201
    # We set these in the class to avoid passing more objects around
    self.selected_release = selected[0]
    self.selected_asset = selected[1]
    self.output("Selected asset '%s' from release '%s'" %
                (self.selected_asset["name"],
                 self.selected_release["name"]))

  def process_release_asset(self):
    """Extract what we need from the release and chosen asset, set env
    variables"""
    tag = self.selected_release["tag_name"]
    # Versioned tags usually start with 'v'
    if tag.startswith("v"):
      tag = tag[1:]

    self.env["url"] = self.selected_asset["browser_download_url"]
    self.env["version"] = tag

  def main(self):
    # Get our list of releases
    releases = self.get_releases(self.env["github_repo"])
    if self.env.get("sort_by_highest_tag_names"):
      from operator import itemgetter

      def loose_compare(this, that):
        from distutils.version import LooseVersion
        return cmp(LooseVersion(this), LooseVersion(that))

      releases = sorted(releases,
                        key=itemgetter("tag_name"),
                        cmp=loose_compare,
                        reverse=True)

    # Store the first eligible asset
    self.select_asset(releases, self.env.get("asset_regex"))

    # Record the url
    self.env["url"] = self.selected_asset["browser_download_url"]

    # Get a version string from the tag name
    # If the version string doesn't start with 'v' and contains
    # the project name, we should remove it
    tag = self.selected_release["tag_name"]
    # Versioned tags usually start with 'v'
    if tag.startswith("v"):
      tag = tag[1:]
    else:
      tag = tag.replace(
          self.env["github_repo"].split('/')[1], '').lstrip('-')
      self.output("Current tag version: %s" % tag)
    self.env["version"] = tag

    # Record release notes
    self.env["release_notes"] = self.selected_release["body"]
    # The API may return a JSON null if no body text was provided,
    # but we cannot ever store a None/NULL in an env.
    if not self.env["release_notes"]:
      self.env["release_notes"] = ""


if __name__ == "__main__":
  PROCESSOR = FBGitHubReleasesInfoProvider()
  PROCESSOR.execute_shell()
