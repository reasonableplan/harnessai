import { motion } from 'framer-motion';

export default function OfficeFurniture() {
  return (
    <g shapeRendering="crispEdges">
      {/* === FLOOR === */}
      <rect x={0} y={200} width={1200} height={500} fill="#C4944A" />
      {/* Floor planks */}
      {Array.from({ length: 12 }).map((_, i) => (
        <line
          key={`plank-h-${i}`}
          x1={0}
          y1={200 + i * 42}
          x2={1200}
          y2={200 + i * 42}
          stroke="#B8860B"
          strokeWidth={1}
          opacity={0.3}
        />
      ))}
      {Array.from({ length: 8 }).map((_, i) => (
        <line
          key={`plank-v-${i}`}
          x1={150 * i + (i % 2 === 0 ? 0 : 75)}
          y1={200}
          x2={150 * i + (i % 2 === 0 ? 0 : 75)}
          y2={700}
          stroke="#B8860B"
          strokeWidth={1}
          opacity={0.2}
        />
      ))}

      {/* === WALLS === */}
      <rect x={0} y={0} width={1200} height={200} fill="#D4A76A" />
      {/* Wall baseboard */}
      <rect x={0} y={192} width={1200} height={10} fill="#8B6914" />
      {/* Wall top trim */}
      <rect x={0} y={0} width={1200} height={6} fill="#8B6914" />

      {/* === RUG === */}
      <rect x={350} y={380} width={300} height={180} rx={4} fill="#8B2252" opacity={0.5} />
      <rect x={358} y={388} width={284} height={164} rx={2} fill="none" stroke="#CD5C5C" strokeWidth={2} opacity={0.6} />
      <rect x={366} y={396} width={268} height={148} rx={2} fill="none" stroke="#DEB887" strokeWidth={1} opacity={0.4} />

      {/* === WINDOW === */}
      <rect x={440} y={30} width={160} height={140} rx={2} fill="#87CEEB" stroke="#8B6914" strokeWidth={4} />
      {/* Window cross */}
      <line x1={520} y1={30} x2={520} y2={170} stroke="#8B6914" strokeWidth={3} />
      <line x1={440} y1={100} x2={600} y2={100} stroke="#8B6914" strokeWidth={3} />
      {/* Clouds through window */}
      <ellipse cx={475} cy={60} rx={18} ry={10} fill="#E0E8F0" opacity={0.8} />
      <ellipse cx={490} cy={56} rx={14} ry={8} fill="#E8EFF5" opacity={0.7} />
      <ellipse cx={560} cy={80} rx={16} ry={8} fill="#E0E8F0" opacity={0.6} />
      {/* Sun */}
      <circle cx={570} cy={52} r={12} fill="#FFE44D" opacity={0.9} />
      {/* Curtains */}
      <rect x={432} y={24} width={14} height={150} fill="#B22222" opacity={0.6} />
      <rect x={594} y={24} width={14} height={150} fill="#B22222" opacity={0.6} />
      <rect x={432} y={22} width={180} height={8} fill="#8B6914" />

      {/* === CEILING LIGHTS === */}
      {[250, 520, 800].map((lx) => (
        <g key={`light-${lx}`}>
          <line x1={lx} y1={0} x2={lx} y2={16} stroke="#666" strokeWidth={2} />
          <rect x={lx - 20} y={14} width={40} height={6} rx={2} fill="#DDD" />
          <motion.rect
            x={lx - 16}
            y={20}
            width={32}
            height={3}
            fill="#FFFACD"
            animate={{ opacity: [0.6, 0.9, 0.6] }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
          />
          {/* Light cone */}
          <polygon
            points={`${lx - 16},23 ${lx + 16},23 ${lx + 40},200 ${lx - 40},200`}
            fill="rgba(255,250,205,0.04)"
          />
        </g>
      ))}

      {/* === POSTERS ON WALL === */}
      {/* Poster 1: "AGENT" */}
      <rect x={100} y={40} width={70} height={90} rx={2} fill="#2C2C54" stroke="#444" strokeWidth={2} />
      <text x={135} y={70} textAnchor="middle" fill="#FFD700" fontSize={9} fontFamily="'Press Start 2P', monospace">
        AGENT
      </text>
      <text x={135} y={86} textAnchor="middle" fill="#61DAFB" fontSize={6} fontFamily="'Press Start 2P', monospace">
        ORCH
      </text>
      <rect x={115} y={96} width={40} height={20} rx={1} fill="#333" />
      <rect x={120} y={100} width={12} height={4} rx={0} fill="#F05032" />
      <rect x={134} y={100} width={16} height={4} rx={0} fill="#68A063" />
      <rect x={120} y={106} width={20} height={4} rx={0} fill="#61DAFB" />

      {/* Poster 2: "CODE" */}
      <rect x={200} y={50} width={65} height={80} rx={2} fill="#1A1A2E" stroke="#444" strokeWidth={2} />
      <text x={232} y={78} textAnchor="middle" fill="#68A063" fontSize={10} fontFamily="'Press Start 2P', monospace">
        CODE
      </text>
      <text x={232} y={95} textAnchor="middle" fill="#F7DF1E" fontSize={5} fontFamily="'Press Start 2P', monospace">
        {"</>"}
      </text>
      <text x={232} y={115} textAnchor="middle" fill="#888" fontSize={5} fontFamily="'Press Start 2P', monospace">
        24/7
      </text>

      {/* Poster 3: "SHIP IT" */}
      <rect x={700} y={45} width={75} height={85} rx={2} fill="#3C1518" stroke="#444" strokeWidth={2} />
      <text x={737} y={72} textAnchor="middle" fill="#FF6B6B" fontSize={8} fontFamily="'Press Start 2P', monospace">
        SHIP
      </text>
      <text x={737} y={88} textAnchor="middle" fill="#FFE66D" fontSize={9} fontFamily="'Press Start 2P', monospace">
        IT!
      </text>
      <rect x={717} y={98} width={40} height={20} fill="none" stroke="#FF6B6B" strokeWidth={1} strokeDasharray="3 2" />
      <text x={737} y={112} textAnchor="middle" fill="#888" fontSize={4} fontFamily="'Press Start 2P', monospace">
        v0.1.0
      </text>

      {/* === CLOCK ON WALL === */}
      <circle cx={650} cy={70} r={22} fill="#FFF8DC" stroke="#8B6914" strokeWidth={3} />
      <circle cx={650} cy={70} r={18} fill="#FFFFF0" />
      {/* Clock marks */}
      {Array.from({ length: 12 }).map((_, i) => {
        const angle = (i * 30 * Math.PI) / 180;
        const x1c = 650 + Math.sin(angle) * 14;
        const y1c = 70 - Math.cos(angle) * 14;
        const x2c = 650 + Math.sin(angle) * 16;
        const y2c = 70 - Math.cos(angle) * 16;
        return (
          <line key={`cm-${i}`} x1={x1c} y1={y1c} x2={x2c} y2={y2c} stroke="#333" strokeWidth={1} />
        );
      })}
      {/* Hour hand */}
      <motion.line
        x1={650}
        y1={70}
        x2={650}
        y2={58}
        stroke="#333"
        strokeWidth={2}
        strokeLinecap="round"
        animate={{ rotate: 360 }}
        transition={{ duration: 43200, repeat: Infinity, ease: 'linear' }}
        style={{ transformOrigin: '650px 70px' }}
      />
      {/* Minute hand */}
      <motion.line
        x1={650}
        y1={70}
        x2={650}
        y2={54}
        stroke="#555"
        strokeWidth={1.5}
        strokeLinecap="round"
        animate={{ rotate: 360 }}
        transition={{ duration: 3600, repeat: Infinity, ease: 'linear' }}
        style={{ transformOrigin: '650px 70px' }}
      />
      <circle cx={650} cy={70} r={2} fill="#333" />

      {/* === DESKS === */}
      {/* Director desk (center-back, larger) */}
      <g>
        <rect x={500} y={270} width={100} height={50} rx={2} fill="#6B4226" stroke="#5A3520" strokeWidth={2} />
        <rect x={504} y={274} width={92} height={42} rx={1} fill="#7B5230" />
        {/* Desk legs */}
        <rect x={504} y={318} width={6} height={14} fill="#5A3520" />
        <rect x={590} y={318} width={6} height={14} fill="#5A3520" />
        {/* Monitor */}
        <rect x={530} y={248} width={36} height={26} rx={2} fill="#222" stroke="#444" strokeWidth={2} />
        <motion.rect
          x={534}
          y={252}
          width={28}
          height={18}
          fill="#1A1A2E"
          animate={{ opacity: [0.85, 1, 0.85] }}
          transition={{ duration: 2, repeat: Infinity }}
        />
        {/* Screen content lines */}
        <rect x={537} y={255} width={14} height={2} fill="#68A063" opacity={0.7} />
        <rect x={537} y={259} width={20} height={2} fill="#61DAFB" opacity={0.5} />
        <rect x={537} y={263} width={10} height={2} fill="#F7DF1E" opacity={0.6} />
        {/* Monitor stand */}
        <rect x={544} y={274} width={8} height={4} fill="#444" />
        {/* Keyboard */}
        <rect x={534} y={282} width={28} height={8} rx={1} fill="#555" />
        <rect x={536} y={284} width={24} height={4} rx={0} fill="#666" />
        {/* Crown badge */}
        <polygon points="548,242 550,238 552,242 554,236 556,242 558,238 560,242" fill="#FFD700" stroke="#DAA520" strokeWidth={0.5} />
      </g>

      {/* Git desk (left side) */}
      <g>
        <rect x={140} y={370} width={90} height={45} rx={2} fill="#6B4226" stroke="#5A3520" strokeWidth={2} />
        <rect x={144} y={374} width={82} height={37} rx={1} fill="#7B5230" />
        <rect x={144} y={413} width={6} height={12} fill="#5A3520" />
        <rect x={220} y={413} width={6} height={12} fill="#5A3520" />
        {/* Monitor */}
        <rect x={165} y={348} width={34} height={24} rx={2} fill="#222" stroke="#444" strokeWidth={2} />
        <motion.rect
          x={169}
          y={352}
          width={26}
          height={16}
          fill="#1A1A2E"
          animate={{ opacity: [0.85, 1, 0.85] }}
          transition={{ duration: 2.3, repeat: Infinity }}
        />
        <rect x={172} y={355} width={18} height={2} fill="#F05032" opacity={0.7} />
        <rect x={172} y={359} width={12} height={2} fill="#AAAAAA" opacity={0.5} />
        <rect x={178} y={374} width={8} height={3} fill="#444" />
        <rect x={168} y={380} width={26} height={7} rx={1} fill="#555" />
      </g>

      {/* Frontend desk (center) */}
      <g>
        <rect x={380} y={430} width={90} height={45} rx={2} fill="#6B4226" stroke="#5A3520" strokeWidth={2} />
        <rect x={384} y={434} width={82} height={37} rx={1} fill="#7B5230" />
        <rect x={384} y={473} width={6} height={12} fill="#5A3520" />
        <rect x={460} y={473} width={6} height={12} fill="#5A3520" />
        {/* Dual monitors */}
        <rect x={393} y={408} width={30} height={24} rx={2} fill="#222" stroke="#444" strokeWidth={2} />
        <motion.rect x={397} y={412} width={22} height={16} fill="#1A1A2E" animate={{ opacity: [0.85, 1, 0.85] }} transition={{ duration: 1.8, repeat: Infinity }} />
        <rect x={400} y={415} width={16} height={2} fill="#61DAFB" opacity={0.7} />
        <rect x={400} y={419} width={10} height={2} fill="#FFB6C1" opacity={0.5} />
        <rect x={427} y={408} width={30} height={24} rx={2} fill="#222" stroke="#444" strokeWidth={2} />
        <motion.rect x={431} y={412} width={22} height={16} fill="#1A1A2E" animate={{ opacity: [0.85, 1, 0.85] }} transition={{ duration: 2.1, repeat: Infinity }} />
        <rect x={434} y={415} width={14} height={2} fill="#E8E8E8" opacity={0.4} />
        <rect x={434} y={419} width={18} height={2} fill="#61DAFB" opacity={0.6} />
        <rect x={410} y={434} width={8} height={3} fill="#444" />
        <rect x={438} y={434} width={8} height={3} fill="#444" />
        <rect x={400} y={442} width={28} height={7} rx={1} fill="#555" />
      </g>

      {/* Backend desk (right side) */}
      <g>
        <rect x={700} y={370} width={90} height={45} rx={2} fill="#6B4226" stroke="#5A3520" strokeWidth={2} />
        <rect x={704} y={374} width={82} height={37} rx={1} fill="#7B5230" />
        <rect x={704} y={413} width={6} height={12} fill="#5A3520" />
        <rect x={780} y={413} width={6} height={12} fill="#5A3520" />
        {/* Monitor */}
        <rect x={725} y={348} width={34} height={24} rx={2} fill="#222" stroke="#444" strokeWidth={2} />
        <motion.rect x={729} y={352} width={26} height={16} fill="#0D1117" animate={{ opacity: [0.85, 1, 0.85] }} transition={{ duration: 2.5, repeat: Infinity }} />
        <rect x={732} y={355} width={8} height={2} fill="#68A063" opacity={0.8} />
        <rect x={742} y={355} width={10} height={2} fill="#AAAAAA" opacity={0.4} />
        <rect x={732} y={359} width={18} height={2} fill="#68A063" opacity={0.5} />
        <rect x={738} y={374} width={8} height={3} fill="#444" />
        <rect x={728} y={380} width={26} height={7} rx={1} fill="#555" />
      </g>

      {/* Docs desk (right corner) */}
      <g>
        <rect x={860} y={430} width={90} height={45} rx={2} fill="#6B4226" stroke="#5A3520" strokeWidth={2} />
        <rect x={864} y={434} width={82} height={37} rx={1} fill="#7B5230" />
        <rect x={864} y={473} width={6} height={12} fill="#5A3520" />
        <rect x={940} y={473} width={6} height={12} fill="#5A3520" />
        {/* Monitor */}
        <rect x={888} y={408} width={34} height={24} rx={2} fill="#222" stroke="#444" strokeWidth={2} />
        <motion.rect x={892} y={412} width={26} height={16} fill="#1A1A2E" animate={{ opacity: [0.85, 1, 0.85] }} transition={{ duration: 2.7, repeat: Infinity }} />
        <rect x={895} y={415} width={20} height={2} fill="#F7DF1E" opacity={0.7} />
        <rect x={895} y={419} width={14} height={2} fill="#AAAAAA" opacity={0.5} />
        <rect x={901} y={434} width={8} height={3} fill="#444" />
        <rect x={891} y={442} width={26} height={7} rx={1} fill="#555" />
        {/* Stack of papers */}
        <rect x={870} y={440} width={14} height={10} fill="#FFFFF0" stroke="#CCC" strokeWidth={0.5} />
        <rect x={872} y={438} width={14} height={10} fill="#FFFFF0" stroke="#CCC" strokeWidth={0.5} />
      </g>

      {/* === CHAIRS === */}
      {/* Director chair */}
      <rect x={535} y={326} width={26} height={20} rx={3} fill="#2C2C54" />
      <rect x={538} y={316} width={20} height={14} rx={2} fill="#3C3C64" />
      {/* Git chair */}
      <rect x={172} y={420} width={22} height={18} rx={3} fill="#8B3A3A" />
      {/* Frontend chair */}
      <rect x={415} y={480} width={22} height={18} rx={3} fill="#2A4A6A" />
      {/* Backend chair */}
      <rect x={733} y={420} width={22} height={18} rx={3} fill="#2A5A2A" />
      {/* Docs chair */}
      <rect x={895} y={480} width={22} height={18} rx={3} fill="#6A5A2A" />

      {/* === BOOKSHELF (right wall area) === */}
      <g>
        <rect x={1020} y={210} width={120} height={180} rx={2} fill="#6B4226" stroke="#5A3520" strokeWidth={3} />
        {/* Shelves */}
        {[240, 280, 320, 360].map((sy) => (
          <rect key={`shelf-${sy}`} x={1024} y={sy} width={112} height={4} fill="#5A3520" />
        ))}
        {/* Books on shelves */}
        {/* Shelf 1 */}
        <rect x={1028} y={215} width={8} height={24} fill="#CC3333" />
        <rect x={1038} y={218} width={7} height={21} fill="#3366CC" />
        <rect x={1047} y={216} width={9} height={23} fill="#33AA55" />
        <rect x={1058} y={220} width={6} height={19} fill="#FF9900" />
        <rect x={1066} y={215} width={8} height={24} fill="#9933CC" />
        <rect x={1076} y={217} width={10} height={22} fill="#CC6633" />
        <rect x={1088} y={219} width={7} height={20} fill="#3399CC" />
        <rect x={1097} y={215} width={9} height={24} fill="#FF6699" />
        <rect x={1108} y={218} width={8} height={21} fill="#66CC33" />
        <rect x={1118} y={216} width={7} height={23} fill="#FFCC00" />
        {/* Shelf 2 */}
        <rect x={1028} y={248} width={10} height={30} fill="#AA4444" />
        <rect x={1040} y={252} width={7} height={26} fill="#4466AA" />
        <rect x={1049} y={249} width={8} height={29} fill="#44AA66" />
        <rect x={1060} y={254} width={12} height={24} fill="#FFAA33" />
        <rect x={1074} y={250} width={6} height={28} fill="#AA44AA" />
        <rect x={1082} y={252} width={9} height={26} fill="#CC8833" />
        <rect x={1094} y={248} width={8} height={30} fill="#44AACC" />
        <rect x={1104} y={251} width={10} height={27} fill="#FF88AA" />
        <rect x={1116} y={249} width={7} height={29} fill="#88CC44" />
        {/* Shelf 3 */}
        <rect x={1028} y={288} width={9} height={30} fill="#DD5555" />
        <rect x={1039} y={290} width={8} height={28} fill="#5577BB" />
        <rect x={1050} y={287} width={7} height={31} fill="#55BB77" />
        <rect x={1060} y={292} width={11} height={26} fill="#FFB366" />
        <rect x={1074} y={289} width={8} height={29} fill="#BB55BB" />
        <rect x={1085} y={291} width={6} height={27} fill="#DD9955" />
        <rect x={1094} y={288} width={10} height={30} fill="#55BBDD" />
        {/* Shelf 4 */}
        <rect x={1028} y={328} width={8} height={30} fill="#EE6666" />
        <rect x={1038} y={332} width={10} height={26} fill="#6688CC" />
        <rect x={1050} y={329} width={7} height={29} fill="#66CC88" />
        <rect x={1060} y={330} width={9} height={28} fill="#FFCC66" />
        <rect x={1072} y={328} width={8} height={30} fill="#CC66CC" />
        <rect x={1082} y={332} width={12} height={26} fill="#EEBB66" />
        {/* Small globe on top shelf */}
        <circle cx={1130} y={228} r={8} fill="#4488AA" stroke="#336688" strokeWidth={1} />
        <ellipse cx={1130} cy={228} rx={8} ry={2} fill="none" stroke="#336688" strokeWidth={0.5} />
      </g>

      {/* === SOFA / LOUNGE (bottom-right) === */}
      <g>
        {/* Sofa back */}
        <rect x={900} y={550} width={180} height={14} rx={4} fill="#8B2252" stroke="#6B1242" strokeWidth={2} />
        {/* Sofa seat */}
        <rect x={904} y={562} width={172} height={28} rx={3} fill="#A0325A" />
        {/* Sofa cushion lines */}
        <line x1={960} y1={562} x2={960} y2={588} stroke="#8B2252" strokeWidth={1} />
        <line x1={1020} y1={562} x2={1020} y2={588} stroke="#8B2252" strokeWidth={1} />
        {/* Sofa arms */}
        <rect x={894} y={548} width={12} height={44} rx={4} fill="#8B2252" stroke="#6B1242" strokeWidth={2} />
        <rect x={1074} y={548} width={12} height={44} rx={4} fill="#8B2252" stroke="#6B1242" strokeWidth={2} />
        {/* Sofa legs */}
        <rect x={908} y={590} width={6} height={6} fill="#5A3520" />
        <rect x={1066} y={590} width={6} height={6} fill="#5A3520" />
        {/* Throw pillows */}
        <rect x={910} y={556} width={18} height={14} rx={3} fill="#FFD700" opacity={0.8} />
        <rect x={1050} y={556} width={18} height={14} rx={3} fill="#61DAFB" opacity={0.8} />
      </g>

      {/* Coffee table */}
      <rect x={940} y={600} width={80} height={30} rx={2} fill="#5A3520" stroke="#4A2510" strokeWidth={2} />
      <rect x={944} y={604} width={72} height={22} rx={1} fill="#6B4226" />
      {/* Magazine on coffee table */}
      <rect x={950} y={608} width={18} height={12} fill="#E8E8E8" stroke="#CCC" strokeWidth={0.5} />
      <rect x={975} y={610} width={14} height={8} fill="#FFE4E1" stroke="#CCC" strokeWidth={0.5} />

      {/* === COFFEE MACHINE === */}
      <g>
        {/* Machine body */}
        <rect x={840} y={540} width={40} height={50} rx={2} fill="#555555" stroke="#444" strokeWidth={2} />
        <rect x={844} y={544} width={32} height={20} rx={1} fill="#333" />
        {/* Display */}
        <rect x={848} y={548} width={24} height={12} rx={1} fill="#003300" />
        <text x={860} y={557} textAnchor="middle" fill="#00FF00" fontSize={5} fontFamily="monospace">
          HOT
        </text>
        {/* Buttons */}
        <circle cx={852} cy={570} r={3} fill="#CC3333" />
        <circle cx={862} cy={570} r={3} fill="#33CC33" />
        <circle cx={872} cy={570} r={3} fill="#3333CC" />
        {/* Drip area */}
        <rect x={852} y={578} width={16} height={10} rx={1} fill="#666" />
        {/* Coffee cup */}
        <rect x={854} y={580} width={10} height={8} rx={1} fill="#FFF8DC" stroke="#DEB887" strokeWidth={1} />
        <rect x={863} y={582} width={4} height={4} rx={2} fill="none" stroke="#DEB887" strokeWidth={1} />
        {/* Steam */}
        <motion.g
          animate={{ opacity: [0, 0.6, 0] }}
          transition={{ duration: 2, repeat: Infinity }}
        >
          <path d="M857,578 Q855,572 858,568" fill="none" stroke="#DDD" strokeWidth={1} opacity={0.5} />
          <path d="M861,578 Q863,571 860,566" fill="none" stroke="#DDD" strokeWidth={1} opacity={0.4} />
        </motion.g>
      </g>

      {/* === PLANTS === */}
      {/* Large plant (left corner) */}
      <g>
        <rect x={40} y={580} width={28} height={30} rx={3} fill="#8B4513" stroke="#6B3410" strokeWidth={2} />
        <rect x={44} y={584} width={20} height={4} fill="#A0522D" />
        {/* Leaves */}
        <ellipse cx={54} cy={560} rx={12} ry={18} fill="#228B22" />
        <ellipse cx={42} cy={555} rx={10} ry={14} fill="#2EA82E" />
        <ellipse cx={64} cy={558} rx={9} ry={16} fill="#1E8B1E" />
        <ellipse cx={48} cy={548} rx={8} ry={12} fill="#32CD32" opacity={0.8} />
        <ellipse cx={58} cy={545} rx={7} ry={10} fill="#228B22" opacity={0.7} />
      </g>

      {/* Small plant on director desk */}
      <g>
        <rect x={508} y={268} width={10} height={12} rx={1} fill="#8B4513" />
        <ellipse cx={513} cy={264} rx={6} ry={8} fill="#228B22" />
        <ellipse cx={510} cy={260} rx={4} ry={6} fill="#2EA82E" />
      </g>

      {/* Cactus near backend desk */}
      <g>
        <rect x={795} y={390} width={10} height={12} rx={1} fill="#CD853F" />
        <rect x={797} y={372} width={6} height={20} rx={3} fill="#2E8B57" />
        <rect x={800} y={376} width={8} height={4} rx={2} fill="#3CB371" />
        <rect x={791} y={380} width={8} height={4} rx={2} fill="#3CB371" />
      </g>

      {/* Hanging plant (right) */}
      <g>
        <line x1={1100} y1={6} x2={1100} y2={50} stroke="#8B6914" strokeWidth={2} />
        <rect x={1088} y={50} width={24} height={16} rx={2} fill="#CD853F" />
        <ellipse cx={1100} cy={48} rx={14} ry={10} fill="#228B22" />
        <ellipse cx={1094} cy={44} rx={8} ry={8} fill="#2EA82E" />
        <ellipse cx={1108} cy={45} rx={7} ry={7} fill="#1E8B1E" />
        {/* Trailing vines */}
        <path d="M1088,58 Q1082,70 1086,80" fill="none" stroke="#228B22" strokeWidth={2} />
        <path d="M1112,58 Q1118,68 1114,78" fill="none" stroke="#2EA82E" strokeWidth={2} />
      </g>

      {/* === WHITEBOARD AREA (back wall) — placeholder rect, WhiteboardMini renders content === */}
      <rect x={810} y={40} width={160} height={120} rx={2} fill="#F0F0F0" stroke="#AAAAAA" strokeWidth={3} />
      <rect x={810} y={36} width={160} height={8} rx={2} fill="#AAAAAA" />
      {/* Whiteboard marker tray */}
      <rect x={830} y={160} width={120} height={6} rx={1} fill="#AAAAAA" />
      <rect x={840} y={158} width={12} height={6} rx={1} fill="#CC3333" />
      <rect x={856} y={158} width={12} height={6} rx={1} fill="#3366CC" />
      <rect x={872} y={158} width={12} height={6} rx={1} fill="#33AA55" />
      {/* "KANBAN" label */}
      <text x={890} y={54} textAnchor="middle" fill="#666" fontSize={6} fontFamily="'Press Start 2P', monospace">
        KANBAN
      </text>

      {/* === MISC DECORATIONS === */}
      {/* Trash can */}
      <rect x={290} y={400} width={16} height={20} rx={1} fill="#666" stroke="#555" strokeWidth={1} />
      <rect x={288} y={398} width={20} height={4} rx={1} fill="#777" />

      {/* Water cooler */}
      <g>
        <rect x={100} y={380} width={20} height={35} rx={2} fill="#B0C4DE" stroke="#8BA8C8" strokeWidth={2} />
        <rect x={104} y={384} width={12} height={14} rx={1} fill="#E0EEFF" />
        <rect x={106} y={410} width={4} height={4} rx={1} fill="#CCCCCC" />
        {/* Water bottle on top */}
        <rect x={104} y={362} width={12} height={20} rx={3} fill="#ADD8E6" opacity={0.7} />
        <rect x={106} y={358} width={8} height={6} rx={1} fill="#87CEEB" opacity={0.8} />
      </g>

      {/* Floor lamp (left of sofa) */}
      <g>
        <rect x={875} y={530} width={4} height={60} fill="#8B6914" />
        <polygon points="862,530 892,530 884,510 870,510" fill="#FFE4B5" stroke="#DEB887" strokeWidth={1} />
        <motion.rect
          x={870}
          y={514}
          width={14}
          height={14}
          fill="#FFFACD"
          opacity={0.3}
          animate={{ opacity: [0.2, 0.4, 0.2] }}
          transition={{ duration: 3, repeat: Infinity }}
        />
      </g>
    </g>
  );
}
