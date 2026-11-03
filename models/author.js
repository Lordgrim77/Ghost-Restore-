const ghostBookshelf = require('./base');
const user = require('./user');

const Author = user.User.extend({
  // Authors/Staff are visible even with 0 posts so new admins and team members show up on /team/
});

const Authors = ghostBookshelf.Collection.extend({
  model: Author,
});

module.exports = {
  Author: ghostBookshelf.model('Author', Author),
  Authors: ghostBookshelf.collection('Authors', Authors),
};
