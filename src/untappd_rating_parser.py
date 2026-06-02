import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional


def _rating_float(value: str) -> Optional[float]:
    if value is None:
        return None
    match = re.search(r"(?<!\d)([0-5](?:\.\d{1,2})?)(?!\d)", str(value))
    if not match:
        return None
    try:
        rating = float(match.group(1))
    except ValueError:
        return None
    return rating if 0.0 <= rating <= 5.0 else None


def _extract_labeled_rating_from_text(text: str, label: str) -> Optional[float]:
    if not text:
        return None
    label_pattern = r"\s*".join(re.escape(part) for part in label.split())
    patterns = [
        rf"{label_pattern}\s*(?:rating)?\s*[:\-(]*\s*([0-5](?:\.\d{{1,2}})?)",
        rf"{label_pattern}.{{0,80}}?([0-5](?:\.\d{{1,2}})?)",
        rf"([0-5](?:\.\d{{1,2}})?).{{0,30}}?{label_pattern}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I | re.S)
        if match:
            rating = _rating_float(match.group(1))
            if rating is not None:
                return rating
    return None


def _attribute_texts(item) -> list[str]:
    values = []
    attrs_to_check = (
        "title",
        "aria-label",
        "data-title",
        "data-original-title",
        "data-rating",
        "data-score",
        "alt",
    )
    for node in item.find_all(True):
        for attr in attrs_to_check:
            value = node.get(attr)
            if value:
                values.append(str(value))
    return values


def _rating_from_class_tokens(item) -> Optional[float]:
    """Extract Untappd-style CSS ratings such as r45 -> 4.5 or r4 -> 4.0."""
    for node in item.find_all(True):
        class_values = node.get("class") or []
        class_text = " ".join(str(value) for value in class_values)
        has_rating_context = bool(re.search(r"rating|star|caps", class_text, flags=re.I))
        for token in class_values:
            match = re.fullmatch(r"r(\d{1,2})", str(token).strip(), flags=re.I)
            if not match:
                continue
            raw = int(match.group(1))
            if not has_rating_context and raw not in range(0, 51):
                continue
            if 0 <= raw <= 5:
                return float(raw)
            if 0 <= raw <= 50:
                return raw / 10.0
    return None


def _extract_labeled_rating(item, label: str) -> Optional[float]:
    texts = []
    full_text = " ".join(item.stripped_strings)
    if full_text:
        texts.append(full_text)
    texts.extend(_attribute_texts(item))

    for text in texts:
        rating = _extract_labeled_rating_from_text(text, label)
        if rating is not None:
            return rating

    pieces = [piece.strip() for piece in item.stripped_strings if piece and piece.strip()]
    for index, piece in enumerate(pieces):
        if label.lower() not in piece.lower():
            continue
        rating = _rating_float(piece)
        if rating is not None:
            return rating
        for offset in range(1, 4):
            if index + offset >= len(pieces):
                break
            rating = _rating_float(pieces[index + offset])
            if rating is not None:
                return rating

    # Some Untappd fragments put the numeric value immediately before the label.
    for index, piece in enumerate(pieces):
        if label.lower() not in piece.lower() or index == 0:
            continue
        for offset in range(1, 3):
            if index - offset < 0:
                break
            rating = _rating_float(pieces[index - offset])
            if rating is not None:
                return rating
    return None


def _extract_checkin_rating(item) -> Optional[float]:
    """Extract the user's rating from a check-in feed item."""
    for label in ("your rating", "you rated", "rating"):
        rating = _extract_labeled_rating(item, label)
        if rating is not None:
            return rating

    for text in _attribute_texts(item):
        rating = _rating_float(text)
        if rating is not None and re.search(r"rating|rated|star|score", text, flags=re.I):
            return rating

    return _rating_from_class_tokens(item)


def _is_missing(value) -> bool:
    if value is None:
        return True
    if value == "":
        return True
    try:
        return bool(value != value)
    except Exception:
        return False


def _raise_if_stopped(stop_requested):
    if stop_requested and stop_requested():
        from app_runtime import TaskCancelled

        raise TaskCancelled()


def _loose_checkin_items_for_ratings(soup):
    """
    Find check-in cards for rating recovery.

    Unlike untapped_selenium.find_checkin_items, this intentionally does not require
    a venue link. Venue links are useful for location recovery, but personal ratings
    should be recoverable from check-ins even when the check-in has no venue.
    """
    import untapped_selenium

    selectors = [
        "div.checkin",
        "div.item",
        "li.item",
        "div[class*='checkin']",
        "div[class*='feed'] div.item",
    ]
    seen = set()
    items = []
    for selector in selectors:
        for node in soup.select(selector):
            beer_link = untapped_selenium.first_matching_anchor(
                node,
                lambda href: href and ("/beer/" in href or "/b/" in href),
            )
            if not beer_link:
                continue
            checkin_id = node.get("data-checkin-id")
            if not checkin_id:
                checkin_parent = node.find_parent(attrs={"data-checkin-id": True})
                if checkin_parent:
                    checkin_id = checkin_parent.get("data-checkin-id")
            node_id = checkin_id or id(node)
            if node_id in seen:
                continue
            seen.add(node_id)
            items.append(node)
    return items


def _parse_checkin_rating_item(item) -> Optional[dict]:
    import untapped_selenium

    try:
        beer_link = untapped_selenium.first_matching_anchor(
            item,
            lambda href: href and ("/beer/" in href or "/b/" in href),
        )
        if not beer_link:
            return None

        brewery_link = untapped_selenium.find_producer_anchor(item)
        beer_name = untapped_selenium.clean_anchor_text(beer_link) or "Unknown"
        brewery_name = untapped_selenium.clean_anchor_text(brewery_link) or "Unknown"

        parsed = {
            "beer_name": beer_name,
            "brewery_name": brewery_name,
            "rating": _extract_checkin_rating(item),
        }

        # Use the existing parser as a fallback for brewery/rating if it succeeds.
        existing = untapped_selenium.parse_checkin_item(item)
        if existing:
            if parsed["brewery_name"] == "Unknown" and existing.get("brewery_name"):
                parsed["brewery_name"] = existing.get("brewery_name")
            if parsed["rating"] is None and existing.get("rating") is not None:
                parsed["rating"] = existing.get("rating")

        return parsed
    except Exception as exc:
        print(f"Warning: Could not parse check-in rating item: {exc}")
        return None


def _fetch_checkin_page_for_ratings(username: str, offset: int, cookies: dict, user_agent: str):
    import requests
    from bs4 import BeautifulSoup
    import untapped_selenium

    url = untapped_selenium.build_checkin_page_url(username, offset)
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": f"{untapped_selenium.UNTAPPD_BASE}/user/{username}",
    }
    response = requests.get(url, headers=headers, cookies=cookies, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    return [
        parsed
        for item in _loose_checkin_items_for_ratings(soup)
        if (parsed := _parse_checkin_rating_item(item))
    ]


def _collect_checkin_rating_matches_parallel(
    username: str,
    target_keys: set[str],
    cookies: dict,
    user_agent: str,
    stop_requested=None,
    max_checkins: Optional[int] = None,
    max_pages: int = 80,
    max_workers: int = 4,
    batch_size: int = 8,
) -> dict[str, float]:
    import untapped_selenium

    matches = {}
    effective_max_pages = max_pages
    if max_checkins is not None:
        effective_max_pages = max(1, min(max_pages, (max_checkins + 24) // 25))
    offsets = list(range(0, effective_max_pages * 25, 25))
    scanned_checkins = 0
    parsed_items_total = 0
    key_matches_without_rating = 0

    for batch_start in range(0, len(offsets), batch_size):
        _raise_if_stopped(stop_requested)
        if target_keys and target_keys.issubset(matches):
            break
        if max_checkins is not None and scanned_checkins >= max_checkins:
            break

        batch_offsets = offsets[batch_start: batch_start + batch_size]
        print(
            "Checking check-in ratings pages "
            f"{batch_start + 1}-{batch_start + len(batch_offsets)} in parallel..."
        )
        results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_offset = {
                executor.submit(
                    _fetch_checkin_page_for_ratings,
                    username,
                    offset,
                    cookies,
                    user_agent,
                ): offset
                for offset in batch_offsets
            }
            for future in as_completed(future_to_offset):
                offset = future_to_offset[future]
                try:
                    results[offset] = future.result()
                except Exception as exc:
                    print(f"Warning: Check-in rating page offset {offset} failed over HTTP: {exc}")
                    results[offset] = []

        saw_items = False
        batch_had_short_page = False
        for offset in sorted(results):
            items = results[offset]
            parsed_items_total += len(items)
            if items:
                saw_items = True
            if len(items) < 10:
                batch_had_short_page = True
            scanned_checkins += len(items)
            for parsed in items:
                key = untapped_selenium.beer_producer_key(
                    parsed.get("beer_name"),
                    parsed.get("brewery_name"),
                )
                rating = parsed.get("rating")
                if key in target_keys and rating is not None and key not in matches:
                    matches[key] = rating
                elif key in target_keys and rating is None:
                    key_matches_without_rating += 1

        if not saw_items or batch_had_short_page:
            break

    print(
        "Parallel check-in scan parsed "
        f"{parsed_items_total:,} check-in rows and recovered {len(matches):,} missing personal ratings."
    )
    if key_matches_without_rating:
        print(
            "Warning: matched "
            f"{key_matches_without_rating:,} missing beer rows in check-ins, but no rating was visible in those check-in cards."
        )
    return matches


def _collect_checkin_rating_matches_with_selenium(
    driver,
    username: str,
    target_keys: set[str],
    stop_requested=None,
    max_checkins: Optional[int] = None,
    max_pages: int = 80,
) -> dict[str, float]:
    from bs4 import BeautifulSoup
    import untapped_selenium

    matches = {}
    scanned_checkins = 0
    next_url = untapped_selenium.build_checkin_page_url(username)
    parsed_items_total = 0
    key_matches_without_rating = 0
    for page_num in range(1, max_pages + 1):
        _raise_if_stopped(stop_requested)
        if target_keys and target_keys.issubset(matches):
            break
        if max_checkins is not None and scanned_checkins >= max_checkins:
            break

        print(f"Checking check-in ratings page {page_num} with Selenium...")
        if page_num == 1:
            driver.get(next_url)
            import time

            time.sleep(1.2)
            soup = BeautifulSoup(driver.page_source, "html.parser")
        else:
            soup = untapped_selenium.fetch_more_feed_page(driver, username, next_url)

        checkin_items = _loose_checkin_items_for_ratings(soup)
        if not checkin_items:
            break
        scanned_checkins += len(checkin_items)
        parsed_items_total += len(checkin_items)
        for item in checkin_items:
            parsed = _parse_checkin_rating_item(item)
            if not parsed:
                continue
            key = untapped_selenium.beer_producer_key(parsed.get("beer_name"), parsed.get("brewery_name"))
            rating = parsed.get("rating")
            if key in target_keys and rating is not None and key not in matches:
                matches[key] = rating
            elif key in target_keys and rating is None:
                key_matches_without_rating += 1
        last_checkin_id = untapped_selenium.find_last_checkin_id(checkin_items)
        if not last_checkin_id:
            break
        next_url = untapped_selenium.build_more_feed_url(username, last_checkin_id)

    print(
        "Selenium check-in scan parsed "
        f"{parsed_items_total:,} check-in rows and recovered {len(matches):,} missing personal ratings."
    )
    if key_matches_without_rating:
        print(
            "Warning: Selenium matched "
            f"{key_matches_without_rating:,} missing beer rows in check-ins, but no rating was visible in those check-in cards."
        )
    return matches


def _fill_missing_personal_ratings_from_checkins(driver, username: str, df, stop_requested=None):
    import untapped_selenium

    if df.empty or "your_rating" not in df.columns:
        return df

    missing_keys = set()
    for _, row in df.iterrows():
        if not _is_missing(row.get("your_rating")):
            continue
        key = untapped_selenium.beer_producer_key(row.get("beer_name"), row.get("brewery_name"))
        if key:
            missing_keys.add(key)

    if not missing_keys:
        return df

    print(f"Recovering missing personal ratings from check-ins ({len(missing_keys)} beers missing)...")
    cookies = {cookie["name"]: cookie["value"] for cookie in driver.get_cookies()}
    user_agent = driver.execute_script("return navigator.userAgent") or (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    )
    rating_matches = _collect_checkin_rating_matches_parallel(
        username,
        missing_keys,
        cookies=cookies,
        user_agent=user_agent,
        stop_requested=stop_requested,
        max_checkins=max(len(df) * 3, len(df)),
        max_workers=4,
    )

    remaining_keys = missing_keys - set(rating_matches)
    if remaining_keys:
        print(
            "Parallel check-in scan did not find all personal ratings; "
            f"using Selenium for {len(remaining_keys)} remaining beers..."
        )
        selenium_matches = _collect_checkin_rating_matches_with_selenium(
            driver,
            username,
            remaining_keys,
            stop_requested=stop_requested,
            max_checkins=max(len(df) * 3, len(df)),
        )
        rating_matches.update(selenium_matches)

    if not rating_matches:
        print("Warning: Could not recover any missing personal ratings from check-ins.")
        return df

    enriched = df.copy()
    filled_count = 0
    for idx, row in enriched.iterrows():
        if not _is_missing(row.get("your_rating")):
            continue
        key = untapped_selenium.beer_producer_key(row.get("beer_name"), row.get("brewery_name"))
        rating = rating_matches.get(key)
        if rating is not None:
            enriched.at[idx, "your_rating"] = rating
            filled_count += 1

    print(f"Recovered personal ratings for {filled_count:,} beer rows from check-ins.")
    return enriched


def patch_untappd_selenium_rating_parser():
    """Patch Untappd Selenium parsing with more defensive rating extraction and recovery."""
    import untapped_selenium

    original_parse_beer = untapped_selenium.parse_beer_item
    if not getattr(original_parse_beer, "_rating_parser_patched", False):
        def parse_beer_item_with_robust_ratings(item):
            parsed = original_parse_beer(item)
            if not parsed:
                return parsed

            if parsed.get("your_rating") is None:
                parsed["your_rating"] = _extract_labeled_rating(item, "your rating")
            if parsed.get("global_rating") is None:
                parsed["global_rating"] = _extract_labeled_rating(item, "global rating")

            return parsed

        parse_beer_item_with_robust_ratings._rating_parser_patched = True
        untapped_selenium.parse_beer_item = parse_beer_item_with_robust_ratings

    original_parse_checkin = untapped_selenium.parse_checkin_item
    if not getattr(original_parse_checkin, "_rating_parser_patched", False):
        def parse_checkin_item_with_robust_rating(item):
            parsed = original_parse_checkin(item)
            if not parsed:
                return parsed
            if parsed.get("rating") is None:
                parsed["rating"] = _extract_checkin_rating(item)
            return parsed

        parse_checkin_item_with_robust_rating._rating_parser_patched = True
        untapped_selenium.parse_checkin_item = parse_checkin_item_with_robust_rating

    original_enrich_consumed_locations = untapped_selenium.enrich_consumed_locations
    if not getattr(original_enrich_consumed_locations, "_rating_recovery_patched", False):
        def enrich_consumed_locations_with_rating_recovery(driver, username, df, stop_requested=None):
            rating_enriched = _fill_missing_personal_ratings_from_checkins(
                driver,
                username,
                df,
                stop_requested=stop_requested,
            )
            return original_enrich_consumed_locations(
                driver,
                username,
                rating_enriched,
                stop_requested=stop_requested,
            )

        enrich_consumed_locations_with_rating_recovery._rating_recovery_patched = True
        untapped_selenium.enrich_consumed_locations = enrich_consumed_locations_with_rating_recovery
