import express from 'express';
import Database from 'better-sqlite3';

const app = express();

app.use(express.json());

app.get('/', (req, res) => {
  return res.status(200).send({'message': 'SHIPTIVITY API. Read documentation to see API docs'});
});

// We are keeping one connection alive for the rest of the life application for simplicity
const db = new Database('./clients.db');

// Don't forget to close connection when server gets terminated
const closeDb = () => db.close();

const validStatuses = ['backlog', 'in-progress', 'complete'];
process.on('SIGTERM', closeDb);
process.on('SIGINT', closeDb);

/**
 * Validate id input
 * @param {any} id
 */
const validateId = (id) => {
  if (Number.isNaN(id)) {
    return {
      valid: false,
      messageObj: {
      'message': 'Invalid id provided.',
      'long_message': 'Id can only be integer.',
      },
    };
  }
  const client = db.prepare('select * from clients where id = ? limit 1').get(id);
  if (!client) {
    return {
      valid: false,
      messageObj: {
      'message': 'Invalid id provided.',
      'long_message': 'Cannot find client with that id.',
      },
    };
  }
  return {
    valid: true,
  };
}

/**
 * Validate priority input
 * @param {any} priority
 */
const validatePriority = (priority) => {
  if (Number.isNaN(priority)) {
    return {
      valid: false,
      messageObj: {
      'message': 'Invalid priority provided.',
      'long_message': 'Priority can only be positive integer.',
      },
    };
  }
  return {
    valid: true,
  }
}

/**
 * Get all of the clients. Optional filter 'status'
 * GET /api/v1/clients?status={status} - list all clients, optional parameter status: 'backlog' | 'in-progress' | 'complete'
 */
app.get('/api/v1/clients', (req, res) => {
  const status = req.query.status;
  if (status) {
    // status can only be either 'backlog' | 'in-progress' | 'complete'
    if (status !== 'backlog' && status !== 'in-progress' && status !== 'complete') {
      return res.status(400).send({
        'message': 'Invalid status provided.',
        'long_message': 'Status can only be one of the following: [backlog | in-progress | complete].',
      });
    }
    const clients = db.prepare('select * from clients where status = ?').all(status);
    return res.status(200).send(clients);
  }
  const statement = db.prepare('select * from clients');
  const clients = statement.all();
  return res.status(200).send(clients);
});

/**
 * Get a client based on the id provided.
 * GET /api/v1/clients/{client_id} - get client by id
 */
app.get('/api/v1/clients/:id', (req, res) => {
  const id = parseInt(req.params.id , 10);
  const { valid, messageObj } = validateId(id);
  if (!valid) {
    return res.status(400).send(messageObj);
  }
  return res.status(200).send(db.prepare('select * from clients where id = ?').get(id));
});

/**
 * Update client information based on the parameters provided.
 * When status is provided, the client status will be changed
 * When priority is provided, the client priority will be changed with the rest of the clients accordingly
 * Note that priority = 1 means it has the highest priority (should be on top of the swimlane).
 * No client on the same status should not have the same priority.
 * This API should return list of clients on success
 *
 * PUT /api/v1/clients/{client_id} - change the status of a client
 *    Data:
 *      status (optional): 'backlog' | 'in-progress' | 'complete',
 *      priority (optional): integer,
 *
 */
app.put('/api/v1/clients/:id', (req, res) => {
  const id = parseInt(req.params.id , 10);
  const { valid, messageObj } = validateId(id);
  if (!valid) {
    return res.status(400).send(messageObj);
  }

  let { status, priority } = req.body;
  let clients = db.prepare('select * from clients').all();
  const client = clients.find(client => client.id === id);

  /* ---------- Update code below ----------*/

  if (status !== undefined && !validStatuses.includes(status)) {
    return res.status(400).send({
      'message': 'Invalid status provided.',
      'long_message': 'Status can only be one of the following: [backlog | in-progress | complete].',
    });
  }

  if (priority !== undefined) {
    priority = parseInt(priority, 10);
    const { valid: validPriorityInput, messageObj: priorityMessageObj } = validatePriority(priority);
    if (!validPriorityInput || priority < 1) {
      return res.status(400).send(priorityMessageObj || {
        'message': 'Invalid priority provided.',
        'long_message': 'Priority can only be positive integer.',
      });
    }
  }

  const oldStatus = client.status;
  const newStatus = status || oldStatus;

  // Lanes ordered by current priority, with the moving client taken out
  const lane = (laneStatus) => clients
    .filter(c => c.status === laneStatus && c.id !== id)
    .sort((a, b) => a.priority - b.priority);

  const newLane = lane(newStatus);

  // No priority given: keep the client where it is within its lane, or append to the bottom of a new lane
  let insertIndex;
  if (priority !== undefined) {
    insertIndex = Math.min(priority - 1, newLane.length);
  } else if (newStatus === oldStatus) {
    insertIndex = Math.min(lane(oldStatus).filter(c => c.priority < client.priority).length, newLane.length);
  } else {
    insertIndex = newLane.length;
  }
  newLane.splice(insertIndex, 0, { ...client, status: newStatus });

  // Renumber affected lanes from 1..n so priorities stay unique and contiguous per status
  const updates = newLane.map((c, index) => ({ id: c.id, status: newStatus, priority: index + 1 }));
  if (newStatus !== oldStatus) {
    lane(oldStatus).forEach((c, index) => updates.push({ id: c.id, status: oldStatus, priority: index + 1 }));
  }

  const updateStatement = db.prepare('update clients set status = ?, priority = ? where id = ?');
  db.transaction((rows) => {
    rows.forEach(({ id, status, priority }) => updateStatement.run(status, priority, id));
  })(updates);

  clients = db.prepare('select * from clients').all();
  return res.status(200).send(clients);
});

app.listen(3001);
console.log('app running on port ', 3001);
