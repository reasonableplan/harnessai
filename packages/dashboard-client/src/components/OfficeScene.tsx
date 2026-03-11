import { useOfficeStore } from '@/stores/office-store';
import OfficeFurniture from './OfficeFurniture';
import WhiteboardMini from './WhiteboardMini';
import AgentCharacter, { getAgentPosition } from './AgentCharacter';

export default function OfficeScene() {
  const agents = useOfficeStore((s) => s.agents);
  const selectedAgent = useOfficeStore((s) => s.selectedAgent);
  const selectAgent = useOfficeStore((s) => s.selectAgent);

  return (
    <div className="relative w-full h-full flex items-center justify-center bg-[#1a1a2e]">
      <svg
        viewBox="0 0 1200 700"
        className="w-full h-full max-h-[calc(100vh-120px)]"
        style={{ imageRendering: 'pixelated' }}
        shapeRendering="crispEdges"
      >
        {/* Background fill */}
        <rect x={0} y={0} width={1200} height={700} fill="#1a1a2e" />

        {/* All furniture, walls, floor, decorations */}
        <OfficeFurniture />

        {/* Whiteboard kanban overlay */}
        <WhiteboardMini />

        {/* Agent characters */}
        {Object.values(agents).map((agent) => {
          const pos = getAgentPosition(agent);
          return (
            <AgentCharacter
              key={agent.id}
              agent={agent}
              x={pos.x}
              y={pos.y}
              onClick={() =>
                selectAgent(selectedAgent === agent.id ? null : agent.id)
              }
              isSelected={selectedAgent === agent.id}
            />
          );
        })}
      </svg>
    </div>
  );
}
