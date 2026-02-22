"""
features/finops.py - Feature 4: Cloud Cost Optimization Agent
Analyzes simulated cloud costs and generates AI-powered savings recommendations.
"""

import random
from datetime import datetime, timedelta
from typing import List, Dict
from loguru import logger


class FinOpsEngine:

    SERVICES = [
        {"name": "compute-prod-cluster",    "type": "Compute",  "daily_cost": 45.20,  "utilization": 78},
        {"name": "compute-staging-cluster", "type": "Compute",  "daily_cost": 38.10,  "utilization": 12},
        {"name": "rds-postgres-primary",    "type": "Database", "daily_cost": 28.40,  "utilization": 65},
        {"name": "rds-postgres-replica-2",  "type": "Database", "daily_cost": 26.80,  "utilization": 4},
        {"name": "s3-logs-archive",         "type": "Storage",  "daily_cost": 12.30,  "utilization": 100},
        {"name": "s3-backup-old-2022",      "type": "Storage",  "daily_cost": 8.90,   "utilization": 0},
        {"name": "elasticache-prod",        "type": "Cache",    "daily_cost": 15.60,  "utilization": 71},
        {"name": "elasticache-dev",         "type": "Cache",    "daily_cost": 14.20,  "utilization": 3},
        {"name": "nat-gateway-us-east",     "type": "Network",  "daily_cost": 9.80,   "utilization": 45},
        {"name": "load-balancer-legacy",    "type": "Network",  "daily_cost": 7.40,   "utilization": 2},
        {"name": "lambda-data-processor",   "type": "Serverless","daily_cost": 3.20,  "utilization": 88},
        {"name": "ec2-bastion-host",        "type": "Compute",  "daily_cost": 5.60,   "utilization": 1},
    ]

    def get_cost_data(self) -> Dict:
        """Generate realistic cloud cost data with waste analysis."""
        services = []
        total_daily = 0
        total_waste = 0

        for svc in self.SERVICES:
            daily = svc["daily_cost"] + random.uniform(-2, 2)
            monthly = daily * 30
            util = svc["utilization"] + random.randint(-3, 3)
            util = max(0, min(100, util))

            # Classify waste level
            if util < 10:
                waste_level = "CRITICAL"
                waste_daily = daily * 0.85
            elif util < 30:
                waste_level = "HIGH"
                waste_daily = daily * 0.5
            elif util < 60:
                waste_level = "MEDIUM"
                waste_daily = daily * 0.2
            else:
                waste_level = "LOW"
                waste_daily = 0

            total_daily += daily
            total_waste += waste_daily

            services.append({
                "name": svc["name"],
                "type": svc["type"],
                "daily_cost": round(daily, 2),
                "monthly_cost": round(monthly, 2),
                "utilization": util,
                "waste_level": waste_level,
                "waste_daily": round(waste_daily, 2),
                "waste_monthly": round(waste_daily * 30, 2),
            })

        # Daily trend (last 14 days)
        trend = []
        for i in range(14):
            d = datetime.now() - timedelta(days=13 - i)
            trend.append({
                "date": d.strftime("%b %d"),
                "compute": round(88 + random.uniform(-8, 8), 2),
                "database": round(55 + random.uniform(-5, 5), 2),
                "storage": round(21 + random.uniform(-2, 2), 2),
                "network": round(17 + random.uniform(-3, 3), 2),
                "total": round(181 + random.uniform(-15, 15), 2),
            })

        return {
            "services": services,
            "trend": trend,
            "summary": {
                "total_daily": round(total_daily, 2),
                "total_monthly": round(total_daily * 30, 2),
                "total_waste_daily": round(total_waste, 2),
                "total_waste_monthly": round(total_waste * 30, 2),
                "savings_percent": round((total_waste / total_daily) * 100, 1),
                "critical_resources": len([s for s in services if s["waste_level"] == "CRITICAL"]),
                "last_updated": datetime.now().strftime("%H:%M:%S"),
            }
        }

    def generate_llm_recommendations(self, cost_data: Dict) -> List[Dict]:
        """Generate AI-powered cost recommendations."""
        recommendations = []
        for svc in cost_data["services"]:
            if svc["waste_level"] == "CRITICAL":
                recommendations.append({
                    "priority": "🔴 CRITICAL",
                    "resource": svc["name"],
                    "type": svc["type"],
                    "finding": f"Resource running at only {svc['utilization']}% utilization",
                    "recommendation": self._get_recommendation(svc),
                    "monthly_savings": svc["waste_monthly"],
                    "risk": "Low",
                    "effort": "30 minutes",
                })
            elif svc["waste_level"] == "HIGH":
                recommendations.append({
                    "priority": "🟡 HIGH",
                    "resource": svc["name"],
                    "type": svc["type"],
                    "finding": f"Significantly underutilized at {svc['utilization']}%",
                    "recommendation": self._get_recommendation(svc),
                    "monthly_savings": svc["waste_monthly"],
                    "risk": "Low",
                    "effort": "1 hour",
                })

        # Sort by savings
        recommendations.sort(key=lambda x: x["monthly_savings"], reverse=True)
        return recommendations[:6]

    def _get_recommendation(self, svc: Dict) -> str:
        recs = {
            "Compute":    f"Scale down to 1 replica during off-peak hours. Consider Spot instances for {svc['name']}.",
            "Database":   f"Downsize instance class or eliminate replica. Schedule automated stop/start.",
            "Storage":    f"Enable S3 Intelligent-Tiering or archive to Glacier. Review retention policy.",
            "Cache":      f"Reduce node count or switch to smaller instance. Evaluate if caching is needed.",
            "Network":    f"Review traffic patterns. Consider consolidating NAT gateways.",
            "Serverless": f"Optimize memory allocation and timeout settings.",
        }
        return recs.get(svc["type"], "Review resource allocation and right-size.")