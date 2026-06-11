import os
import sys

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scraper import IndeedScraper

def main():
    workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = os.path.join(workspace_dir, "search_page.html")
    
    if not os.path.exists(html_path):
        print(f"Error: {html_path} does not exist!")
        return

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    scraper = IndeedScraper()
    
    # Test Parse Search Results
    listings = scraper._parse_search_results(html_content)
    print(f"Number of listings extracted: {len(listings)}")
    for i, listing in enumerate(listings[:5]):
        print(f"Listing {i+1}:")
        print(f"  Title: {listing['title']}")
        print(f"  Company: {listing['company']}")
        print(f"  Location: {listing['location']}")
        print(f"  Date Posted: {listing['date_posted']}")
        print(f"  Job Type: {listing['job_type']}")
        print(f"  Detail URL: {listing['detail_url']}")
        print("-" * 40)
        
    # Test Has Next Page
    has_next = scraper._has_next_page(html_content)
    print(f"Has next page? {has_next}")

if __name__ == "__main__":
    main()
