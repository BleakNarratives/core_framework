# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: thoth
# ROLE: Undocumented module
# TIER: Scout (6)
# AUTHOR: BleakNarratives
# SESSION: 2026-08-22 ShipWreckD OS Builder — auto-tagged by DNA Sweeper
# [/DNA_TAG]

import os
import sys
import json
import agent_bus
from thoth_adapters import zeroclaw, lough, datacampus, payment_bridge
from higgins_adapter import higgins
from coach_bleak_adapter import coach_bleak
try:
    from mrs_higgins_saas.firefly_scout import FireflyScout
except Exception:
    FireflyScout = None

# Persisted cursor for MotherBrain decision consumption (bus dir).
THOTH_STATE = os.path.join(str(agent_bus.BUS_DIR), "thoth_state.json")


class OfficeManager:
    """Minimal fallback so Thoth can run without the legacy front_desk_lady_v2 import."""

    def announce_completion(self, title, message):
        print(f"[OfficeManager] {title}: {message}")

class ThothCore:
    def __init__(self):
        self.manager = OfficeManager()
        self.scout = FireflyScout(headless=True) if FireflyScout else None
        # Load asset mapping for delivery
        self.asset_map = self._load_asset_map()
        # MotherBrain decision cursor — persisted so restarts don't re-act.
        self.throttled_sources = set()
        self._mb_cursor = self._load_mb_cursor()
        print("[Thoth Core]: Initialized. ModMind Loop active with Asset Mapping.")

    def _load_asset_map(self):
        """Loads SaaS packages to map payment_id to actual assets."""
        mapping = {}
        packages_dir = '/home/bleaknarratives/RootBase/mrs_higgins_saas/saas_packages'
        try:
            for filename in os.listdir(packages_dir):
                if filename.endswith('.json'):
                    with open(os.path.join(packages_dir, filename), 'r') as f:
                        pkg = json.load(f)
                        mapping[pkg['name']] = {
                            "asset_link": f"https://datacampus.local/labs/access?pkg={pkg['tagline'].replace(' ', '_')}",
                            "price": pkg['price_sats']
                        }
        except Exception as e:
            print(f"[Error]: Failed to load asset map: {e}")
        return mapping

    # ---- MotherBrain decision cursor persistence ----
    def _load_mb_cursor(self):
        if os.path.exists(THOTH_STATE):
            try:
                with open(THOTH_STATE, 'r') as f:
                    return json.load(f).get("mb_cursor", 0)
            except Exception:
                return 0
        # First run: start at current bus head so we only act on NEW decisions.
        return agent_bus.current_line_count()

    def _save_mb_cursor(self):
        agent_bus.ensure_bus()
        with open(THOTH_STATE, 'w') as f:
            json.dump({"mb_cursor": self._mb_cursor}, f, indent=2)

    def scout_and_analyze(self):
        print("\n[Thoth]: Deploying Firefly Scouts...")
        if not self.scout:
            print("[Thoth]: FireflyScout unavailable; skipping lead analysis.")
            return False
        raw_leads = self.scout.run()
        if not raw_leads: return False

        high_value_leads = []
        for lead in raw_leads:
            analysis = coach_bleak.analyze_scenario(
                scenario=f"Lead from {lead['board']} for {lead['package']}. Content: {lead['content_snippet']}",
                mode="analysis",
                additional_prompt="Is this a high-intent lead? Answer YES or NO."
            )
            if "YES" in analysis.get("aiResponse", "").upper():
                high_value_leads.append(lead)
        
        for lead in high_value_leads:
            self.generate_revenue(platform=lead['board'])
            
        lough.emit(event_type="scout.leads.processed", payload={"total_found": len(raw_leads), "high_value": len(high_value_leads)})
        return True

    def escalate_to_bleak(self, client_id, amount_sats, days_overdue):
        print(f"\n[Thoth]: Escalating client {client_id} to Coach Bleak...")
        pressure_res = coach_bleak.generate_pressure_notice(client_id, amount_sats, days_overdue)
        if "error" in pressure_res: return False

        lough.emit(event_type="revenue.escalation.bleak", payload={"client_id": client_id, "amount": amount_sats, "days": days_overdue})
        self.manager.announce_completion("Escalation Active", f"Client {client_id} handed to Bleak.")
        return True

    def generate_revenue(self, platform="Nostr"):
        print(f"\n[Thoth]: Activating Revenue Stream on {platform}...")
        routing_res = higgins.route_packages(platform_filter=platform)
        if routing_res["exit_code"] != 0: return False

        copy_res = higgins.generate_promo_copy("", platform=platform)
        copy_text = copy_res["stdout"]
        if not copy_text: return False

        if platform == "Nostr":
            higgins.post_to_nostr(copy_text)

        lough.emit(event_type="revenue.stream.activated", payload={"platform": platform, "status": "published"})
        self.manager.announce_completion("Revenue Push", f"Packages routed to {platform}.")
        return True

    def deploy_lab_workflow(self, cohort_id, lab_id, capabilities, assignment_name="Quick Capital Lab"):
        print(f"\n[Thoth]: Initiating workflow for {assignment_name}...")
        assignment = datacampus.create_assignment(cohort_id, lab_id)
        if "error" in str(assignment): return False

        assignment_id = getattr(assignment, 'assignment_id', 'unknown')
        task = zeroclaw.create_task(assignment_id, lab_id, capabilities)
        if isinstance(task, dict) and "error" in task: return False

        lough.emit(event_type="swarm.workflow.started", payload={"assignment_id": assignment_id, "lab_id": lab_id})
        self.manager.announce_completion(assignment_name, f"Lab {lab_id} live in ZeroClaw.")
        return True

    def verify_and_unlock(self, payment_id, customer_id, amount_sats):
        print(f"\n[Thoth]: Verifying payment {payment_id} for customer {customer_id}...")
        
        if payment_bridge.check_invoice_status(payment_id) != "PAID":
            print(f"[Thoth]: Payment {payment_id} not paid. No unlock.")
            return False

        res = zeroclaw.verify_payment(payment_id, customer_id, amount_sats)
        if isinstance(res, dict) and "error" in res: return False

        delivery_success = self.execute_delivery(payment_id, customer_id)
        lough.emit(event_type="payment.confirmed", payload={"payment_id": payment_id, "amount": amount_sats, "delivery": delivery_success})
        self.manager.announce_completion("ModMind Loop Closed", f"Payment {payment_id} verified. Product shipped.")
        return True

    def execute_delivery(self, payment_id, customer_id):
        print(f"[DeliveryEngine]: Shipping asset for {payment_id} to {customer_id}...")
        # Use asset_map to find the product link
        # In a real system, we'd look up the package by payment_id in a database
        # Here we match based on a mock link for the demonstration of the loop
        product_link = "https://datacampus.local/access/general"
        for name, data in self.asset_map.items():
            if data['price'] == 100000: # Example match logic
                product_link = data['asset_link']
                break
        
        lough.emit(event_type="delivery.executed", payload={"payment_id": payment_id, "asset": product_link}, location="thoth_core")
        return True

    def swarm_audit(self):
        print("\n--- Swarm Audit ---")
        print(f"ZeroClaw Status: {zeroclaw.get_status()}")
        print(f"Lough Heartbeat: {'Active' if 'error' not in str(lough.poll()) else 'Offline'}")
        print("------------------\n")

    # ---- MotherBrain -> Thoth action loop ----
    def act_on_decisions(self, limit=100):
        """Read motherbrain.decision events from agent_bus and act on them.

        Closes the loop: MotherBrain analyzes + decides, Thoth executes.
        Cursor persisted in thoth_state.json so restarts don't re-act.
        Returns a summary of actions taken.
        """
        events, next_offset = agent_bus.read_events(offset=self._mb_cursor, limit=limit)
        actions = []
        for event in events:
            if event.get("event_type") != "motherbrain.decision":
                continue
            action = self._execute_decision(event.get("payload", {}))
            if action:
                actions.append(action)
        self._mb_cursor = next_offset
        self._save_mb_cursor()
        return {"actions": actions, "processed": len(events)}

    def _execute_decision(self, decision):
        """Dispatch a single MotherBrain decision to the right Thoth action.

        Returns a dict describing the action (or None for no-op).
        Extend this dispatch as MotherBrain grows new decision types.
        """
        kind = decision.get("decision")
        if kind == "throttle":
            target = decision.get("target_source", "unknown")
            self.throttled_sources.add(target)
            print(f"[Thoth]: Throttle acknowledged for source '{target}'.")
            action = {"action": "throttle_acknowledged", "target_source": target}
        elif kind == "revenue_push":
            platform = decision.get("platform", "Nostr")
            print(f"[Thoth]: Revenue push triggered by MotherBrain for {platform}.")
            ok = self.generate_revenue(platform=platform)
            action = {"action": "revenue_push", "platform": platform, "ok": ok}
        elif kind == "idle":
            action = None  # no-op
        else:
            print(f"[Thoth]: Unknown MotherBrain decision '{kind}'.")
            action = {"action": "unknown_decision", "decision": kind}

        if action is not None:
            agent_bus.emit_event(
                "thoth.action",
                payload=action,
                source="thoth",
                channel="thoth",
                tags=["action"],
            )
        return action

if __name__ == "__main__":
    thoth = ThothCore()
    thoth.swarm_audit()
    # Consume any pending MotherBrain decisions.
    result = thoth.act_on_decisions()
    if result["actions"]:
        print(f"[Thoth]: {len(result['actions'])} MotherBrain decision(s) acted on.")
