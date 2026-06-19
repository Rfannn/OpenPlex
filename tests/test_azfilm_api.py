# test_azfilm_api.py
import asyncio
import httpx
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import sys

# Configuration
BASE_URL = "http://127.0.0.1:8185"
API_PREFIX = "/api"
TIMEOUT = 30

# Test user credentials (create these first or use existing)
TEST_USERNAME = "testuser"
TEST_PASSWORD = "testpass123"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_test_header(name: str):
    print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}TEST: {name}{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")

def print_success(msg: str):
    print(f"{Colors.GREEN}✓ {msg}{Colors.RESET}")

def print_error(msg: str):
    print(f"{Colors.RED}✗ {msg}{Colors.RESET}")

def print_info(msg: str):
    print(f"{Colors.YELLOW}ℹ {msg}{Colors.RESET}")

async def get_auth_token(client: httpx.AsyncClient) -> Optional[str]:
    """Get authentication token by logging in"""
    print_test_header("Authentication")
    
    # Try to register first (in case user doesn't exist)
    print_info("Attempting to register test user...")
    try:
        register_response = await client.post(
            f"{BASE_URL}{API_PREFIX}/auth/register",
            json={
                "username": TEST_USERNAME,
                "password": TEST_PASSWORD,
                "display_name": "Test User"
            },
            timeout=TIMEOUT
        )
        
        if register_response.status_code == 200:
            print_success(f"Registered new user: {TEST_USERNAME}")
        elif register_response.status_code == 400:
            print_info("User already exists, will try to login")
        else:
            print_info(f"Register returned: {register_response.status_code}")
    except Exception as e:
        print_info(f"Register attempt: {str(e)}")
    
    # Login
    print_info(f"Logging in as {TEST_USERNAME}...")
    try:
        login_response = await client.post(
            f"{BASE_URL}{API_PREFIX}/auth/login",
            json={
                "username": TEST_USERNAME,
                "password": TEST_PASSWORD
            },
            timeout=TIMEOUT
        )
        
        if login_response.status_code == 200:
            data = login_response.json()
            token = data.get("token")
            print_success(f"Login successful! Got token: {token[:20]}...")
            return token
        else:
            print_error(f"Login failed: {login_response.status_code} - {login_response.text}")
            return None
    except Exception as e:
        print_error(f"Login error: {str(e)}")
        return None

async def test_search_azfilm(client: httpx.AsyncClient, token: str, query: str = "inception") -> Dict[str, Any]:
    """Test AzFilm search endpoint"""
    print_test_header(f"AzFilm Search API - Query: '{query}'")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = await client.get(
            f"{BASE_URL}{API_PREFIX}/azfilm/search",
            params={"q": query},
            headers=headers,
            timeout=TIMEOUT
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("results"):
                results = data["results"]
                print_success(f"Search successful! Found {len(results)} results")
                
                # Display first few results
                for i, result in enumerate(results[:5], 1):
                    print(f"\n  {i}. {Colors.BOLD}{result.get('title', 'N/A')}{Colors.RESET}")
                    print(f"     IMDb ID: {result.get('imdb_id', 'N/A')}")
                    print(f"     Year: {result.get('year', 'N/A')}")
                    print(f"     Type: {result.get('media_type', 'N/A')}")
                    print(f"     Rating: {result.get('imdb_rating', 'N/A')}")
                    print(f"     Subtitles: {', '.join(result.get('subtitle_types', []))}")
                
                return {"success": True, "count": len(results), "results": results}
            else:
                print_error("No results found in response")
                return {"success": False, "error": "No results"}
        elif response.status_code == 401:
            print_error("Authentication failed - token may be invalid")
            return {"success": False, "error": "Authentication failed"}
        else:
            print_error(f"HTTP {response.status_code}: {response.text[:200]}")
            return {"success": False, "error": f"HTTP {response.status_code}"}
            
    except httpx.TimeoutException:
        print_error("Request timeout - Server might be slow or down")
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        print_error(f"Exception: {str(e)}")
        return {"success": False, "error": str(e)}

async def test_azfilm_links(client: httpx.AsyncClient, token: str, imdb_id: str = "tt1375666") -> Dict[str, Any]:
    """Test AzFilm get links endpoint"""
    print_test_header(f"AzFilm Get Links API - IMDb ID: {imdb_id}")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = await client.get(
            f"{BASE_URL}{API_PREFIX}/azfilm/links/{imdb_id}",
            headers=headers,
            timeout=TIMEOUT
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("links"):
                links = data["links"]
                total_links = sum(len(v) for v in links.values())
                print_success(f"Links retrieved successfully! Found {total_links} total links")
                
                for link_type, link_list in links.items():
                    if link_list:
                        print(f"\n  {Colors.BOLD}{link_type}{Colors.RESET}: {len(link_list)} links")
                        for link in link_list[:3]:  # Show first 3 links
                            print(f"    - {link.get('label', 'N/A')}")
                            print(f"      URL: {link.get('url', 'N/A')[:80]}...")
                            print(f"      Quality: {link.get('quality', 'N/A')}")
                            print(f"      Size: {link.get('size', 'N/A')}")
                
                return {"success": True, "total_links": total_links, "links": links}
            else:
                print_error("No links found in response")
                return {"success": False, "error": "No links"}
        elif response.status_code == 401:
            print_error("Authentication failed - token may be invalid")
            return {"success": False, "error": "Authentication failed"}
        else:
            print_error(f"HTTP {response.status_code}: {response.text[:200]}")
            return {"success": False, "error": f"HTTP {response.status_code}"}
            
    except httpx.TimeoutException:
        print_error("Request timeout - Server might be slow or down")
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        print_error(f"Exception: {str(e)}")
        return {"success": False, "error": str(e)}

async def test_multiple_searches(client: httpx.AsyncClient, token: str):
    """Test multiple search queries"""
    print_test_header("Multiple Search Queries")
    
    queries = ["inception", "the matrix", "breaking bad", "friends", "interstellar"]
    results_summary = []
    headers = {"Authorization": f"Bearer {token}"}
    
    for query in queries:
        print_info(f"Searching for '{query}'...")
        try:
            response = await client.get(
                f"{BASE_URL}{API_PREFIX}/azfilm/search",
                params={"q": query},
                headers=headers,
                timeout=TIMEOUT
            )
            
            if response.status_code == 200:
                data = response.json()
                count = len(data.get("results", []))
                if count > 0:
                    print_success(f"  Found {count} results")
                    results_summary.append({"query": query, "count": count, "success": True})
                else:
                    print_info(f"  No results for '{query}'")
                    results_summary.append({"query": query, "count": 0, "success": True})
            elif response.status_code == 401:
                print_error(f"  Authentication failed for '{query}'")
                results_summary.append({"query": query, "count": 0, "success": False})
            else:
                print_error(f"  HTTP {response.status_code} for '{query}'")
                results_summary.append({"query": query, "count": 0, "success": False})
        except Exception as e:
            print_error(f"  Error for '{query}': {str(e)}")
            results_summary.append({"query": query, "count": 0, "success": False})
    
    # Summary
    print(f"\n{Colors.CYAN}Search Summary:{Colors.RESET}")
    successful = sum(1 for r in results_summary if r["success"])
    total_results = sum(r["count"] for r in results_summary)
    print(f"  Successful queries: {successful}/{len(queries)}")
    print(f"  Total results found: {total_results}")
    
    return results_summary

async def test_download_flow(client: httpx.AsyncClient, token: str):
    """Test complete download flow: search -> get links -> download"""
    print_test_header("Complete Download Flow Test")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Step 1: Search for a movie
    print_info("Step 1: Searching for 'Inception'...")
    search_response = await client.get(
        f"{BASE_URL}{API_PREFIX}/azfilm/search",
        params={"q": "inception"},
        headers=headers
    )
    
    if search_response.status_code != 200:
        print_error(f"Search failed with HTTP {search_response.status_code}")
        return False
    
    search_data = search_response.json()
    results = search_data.get("results", [])
    
    if not results:
        print_error("No search results found - aborting flow test")
        return False
    
    # Find Inception
    inception = None
    for r in results:
        if "inception" in r.get("title", "").lower():
            inception = r
            break
    
    if not inception:
        print_error("Could not find Inception in search results")
        return False
    
    print_success(f"Found: {inception['title']} ({inception['year']}) - IMDb: {inception['imdb_id']}")
    
    # Step 2: Get download links
    print_info(f"Step 2: Getting download links for {inception['imdb_id']}...")
    links_response = await client.get(
        f"{BASE_URL}{API_PREFIX}/azfilm/links/{inception['imdb_id']}",
        headers=headers
    )
    
    if links_response.status_code != 200:
        print_error(f"Failed to get download links: HTTP {links_response.status_code}")
        return False
    
    links_data = links_response.json()
    links = links_data.get("links", {})
    total_links = sum(len(v) for v in links.values())
    
    if total_links == 0:
        print_info("No download links found (this might be normal if movie page is different)")
        # Try alternative: maybe we need to use the URL directly
        print_info("Attempting to fetch from movie URL directly...")
        movie_url = f"{BASE_URL}{API_PREFIX}/azfilm/movie/{inception['imdb_id']}"
        movie_response = await client.get(movie_url, headers=headers)
        if movie_response.status_code == 200:
            print_success("Successfully fetched movie page")
        return False
    
    print_success(f"Found {total_links} download links")
    
    # Step 3: Show available download options
    print_info("Step 3: Available download options:")
    for link_type, link_list in links.items():
        if link_list:
            print(f"  {link_type}:")
            for i, link in enumerate(link_list[:3], 1):
                quality = link.get('quality', 'Unknown')
                size = link.get('size', 'Unknown')
                print(f"    {i}. Quality: {quality}, Size: {size}")
                print(f"       URL: {link.get('url', 'N/A')[:100]}...")
    
    print_success("\n✓ Download flow test completed successfully!")
    return True

async def test_server_health(client: httpx.AsyncClient) -> bool:
    """Test if the main server is running"""
    print_test_header("Server Health Check")
    
    try:
        response = await client.get(f"{BASE_URL}/api/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print_success(f"Server is running at {BASE_URL}")
            print_info(f"  Status: {data.get('status', 'N/A')}")
            print_info(f"  Media Root: {data.get('media_root', 'N/A')}")
            print_info(f"  Disk Free: {data.get('disk_free', 'N/A')} bytes")
            print_info(f"  aria2 Alive: {data.get('aria2_alive', 'N/A')}")
            return True
        else:
            print_error(f"Server returned HTTP {response.status_code}")
            return False
    except httpx.ConnectError:
        print_error(f"Cannot connect to server at {BASE_URL}")
        print_info("Make sure your server is running with: python run.py or .\\run.ps1")
        return False
    except Exception as e:
        print_error(f"Health check failed: {str(e)}")
        return False

async def test_error_handling(client: httpx.AsyncClient, token: str):
    """Test error handling for invalid inputs"""
    print_test_header("Error Handling Tests")
    headers = {"Authorization": f"Bearer {token}"}
    
    tests = [
        ("Empty search query", f"{BASE_URL}{API_PREFIX}/azfilm/search", {"q": ""}),
        ("Missing search query", f"{BASE_URL}{API_PREFIX}/azfilm/search", {}),
        ("Invalid IMDb ID", f"{BASE_URL}{API_PREFIX}/azfilm/links/invalid_id", {}),
        ("Very long query", f"{BASE_URL}{API_PREFIX}/azfilm/search", {"q": "a" * 1000}),
    ]
    
    passed = 0
    for name, url, params in tests:
        try:
            response = await client.get(url, params=params, headers=headers, timeout=TIMEOUT)
            # 400 Bad Request or 422 Unprocessable Entity are expected for invalid inputs
            if response.status_code in [400, 422, 404]:
                print_success(f"  {name}: Properly rejected with HTTP {response.status_code}")
                passed += 1
            elif response.status_code == 200:
                print_info(f"  {name}: Returned HTTP 200 (accepted input that might be invalid)")
            else:
                print_info(f"  {name}: Returned HTTP {response.status_code}")
        except Exception as e:
            print_info(f"  {name}: Exception: {str(e)}")
    
    print_success(f"Error handling: {passed}/{len(tests)} tests passed expectations")

async def main():
    """Main test runner"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}AZFILM API TEST SUITE{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"Server URL: {BASE_URL}")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    async with httpx.AsyncClient() as client:
        # First check if server is running
        if not await test_server_health(client):
            print_error("\nCannot proceed with tests - server is not responding")
            print_info("Please start your server first with: .\\run.ps1 (Windows) or ./run.sh (Linux/Mac)")
            sys.exit(1)
        
        # Get authentication token
        token = await get_auth_token(client)
        if not token:
            print_error("\nCannot proceed with tests - authentication failed")
            print_info("Make sure you have a valid user account")
            sys.exit(1)
        
        # Run all tests
        results = {}
        
        # Test 1: Single search
        search_result = await test_search_azfilm(client, token, "inception")
        results["search"] = search_result.get("success", False)
        
        # Test 2: Get links for a known movie
        links_result = await test_azfilm_links(client, token, "tt1375666")  # Inception
        results["links"] = links_result.get("success", False)
        
        # Test 3: Multiple searches
        await test_multiple_searches(client, token)
        
        # Test 4: Test error handling
        await test_error_handling(client, token)
        
        # Test 5: Complete flow test
        flow_result = await test_download_flow(client, token)
        results["flow"] = flow_result
        
        # Print final summary
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}TEST SUMMARY{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
        
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        
        for test_name, passed_flag in results.items():
            status = f"{Colors.GREEN}✓ PASSED{Colors.RESET}" if passed_flag else f"{Colors.RED}✗ FAILED{Colors.RESET}"
            print(f"  {test_name.upper()}: {status}")
        
        print(f"\n{Colors.BOLD}Overall: {passed}/{total} tests passed{Colors.RESET}")
        
        if passed == total:
            print(f"\n{Colors.GREEN}{Colors.BOLD}All tests passed! The AzFilm API is working correctly.{Colors.RESET}")
        else:
            print(f"\n{Colors.YELLOW}Some tests failed. Please check the errors above.{Colors.RESET}")
            print_info("Make sure you've added the AzFilm endpoints to your downloads.py router")

if __name__ == "__main__":
    asyncio.run(main())