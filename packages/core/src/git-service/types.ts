import type { Octokit } from '@octokit/rest';
import type { graphql } from '@octokit/graphql';

export interface GitHubContext {
  octokit: Octokit;
  graphqlWithAuth: typeof graphql;
  owner: string;
  repo: string;
}

export interface ProjectItemsResponse {
  node: {
    items: {
      nodes: Array<{
        id: string;
        content: {
          id: string;
          number: number;
          title: string;
          body: string;
          assignees: { nodes: Array<{ login: string }> };
          labels: { nodes: Array<{ name: string }> };
        } | null;
        fieldValues: {
          nodes: Array<{
            name?: string;
            field?: { name: string };
          }>;
        };
      }>;
      pageInfo: { hasNextPage: boolean; endCursor: string };
    };
  } | null; // GraphQL node() query can return null
}
