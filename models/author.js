const ghostBookshelf = require('./base');
const user = require('./user');

const ACTIVE_AUTHOR_STATES = ['active', 'warn-1', 'warn-2', 'warn-3', 'warn-4'];

const Author = user.User.extend(
  {
    // Authors/Staff are visible even with 0 posts so new admins and team members show up on /team/,
    // while suspended ('inactive') and locked ('locked') accounts remain hidden on public endpoints.
    enforcedFilters: function enforcedFilters(options) {
      if (options && options.context && options.context.internal) {
        return null;
      }

      return options && options.context && options.context.public
        ? 'status:[' + ACTIVE_AUTHOR_STATES.join(',') + ']'
        : null;
    },
  },
  {
    findOne: function findOne(dataToClone, unfilteredOptions) {
      const data = Object.assign({}, dataToClone);
      if (
        unfilteredOptions &&
        unfilteredOptions.context &&
        unfilteredOptions.context.public &&
        !data.status
      ) {
        data.status = 'active';
      }
      return user.User.findOne.call(this, data, unfilteredOptions);
    },
  },
);

const Authors = ghostBookshelf.Collection.extend({
  model: Author,
});

module.exports = {
  Author: ghostBookshelf.model('Author', Author),
  Authors: ghostBookshelf.collection('Authors', Authors),
};
