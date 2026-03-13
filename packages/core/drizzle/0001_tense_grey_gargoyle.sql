CREATE TABLE "agent_config" (
	"agent_id" text PRIMARY KEY NOT NULL,
	"claude_model" text DEFAULT 'claude-sonnet-4-20250514' NOT NULL,
	"max_tokens" integer DEFAULT 4096 NOT NULL,
	"temperature" real DEFAULT 0.7 NOT NULL,
	"token_budget" integer DEFAULT 10000000 NOT NULL,
	"task_timeout_ms" integer DEFAULT 300000 NOT NULL,
	"poll_interval_ms" integer DEFAULT 10000 NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "hooks" (
	"id" text PRIMARY KEY NOT NULL,
	"event" text NOT NULL,
	"name" text NOT NULL,
	"description" text,
	"enabled" boolean DEFAULT true NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "agent_config" ADD CONSTRAINT "agent_config_agent_id_agents_id_fk" FOREIGN KEY ("agent_id") REFERENCES "public"."agents"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "idx_messages_type" ON "messages" USING btree ("type");--> statement-breakpoint
CREATE INDEX "idx_messages_trace_id" ON "messages" USING btree ("trace_id");--> statement-breakpoint
CREATE INDEX "idx_tasks_board_column" ON "tasks" USING btree ("board_column");--> statement-breakpoint
CREATE INDEX "idx_tasks_assigned_agent" ON "tasks" USING btree ("assigned_agent");--> statement-breakpoint
CREATE INDEX "idx_tasks_epic_id" ON "tasks" USING btree ("epic_id");--> statement-breakpoint
CREATE INDEX "idx_tasks_status" ON "tasks" USING btree ("status");--> statement-breakpoint
CREATE INDEX "idx_tasks_github_issue" ON "tasks" USING btree ("github_issue_number");