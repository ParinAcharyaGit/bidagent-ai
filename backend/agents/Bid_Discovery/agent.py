"""
Bid Discovery Agent

The purpose of this agent is to discover and filter procurement bids based on user-defined keywords and web search.

FEATURES:
 - Upon trigger, crawls procurement portals for bids
 - INPUTS: User's industry profile, keywords, NAICS/UNSPSC codes, geographic preferences, existing bid portals to monitor.
 - Navigates identified portals, completes login and CAPTCHA challenges, and extracts bid data, descriptions, deadlines, links to documents etc
 - Performs relevance filtering and sorting
 - LOGIN AND PASSWORD MANAGEMENT: Uses credentials stored in Secret Manager to log into portals and Gemini Vision to solve CAPTCHAs, Cloud Run for browser automation


 We could also orchestrate sub agents for specific tasks like:
    1. keyword extraction from user profile
    2. web scraping of procurement portals
    3. displaying results in a user-friendly format

"""
import sys
print(sys.path)
from google.adk.agents.llm_agent import Agent
from ..shared_libraries import constants
from .sub_agents.search_results.agent import bid_search_agent
from .sub_agents.rag_agent.agent import rag_agent
from . import prompt

bid_discovery_manager = Agent(
    name="bid_discovery_manager",
    description="Manages the process of discovering and analyzing new bid opportunities.",
    model=constants.MODEL,
    # tools=[
    #     <specify_tool>,
    # ],  
    instruction=prompt.ROOT_PROMPT,
    sub_agents=[
        bid_search_agent,
        rag_agent
    ],
)
